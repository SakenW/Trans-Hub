# tests/unit/test_persistence.py
"""
针对 `trans_hub.persistence` 模块的单元测试。

这些测试使用内存中的 SQLite 数据库来验证 DefaultPersistenceHandler
的所有数据库操作是否符合预期，包括事务、并发安全和数据完整性。
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from trans_hub.db.schema_manager import MIGRATIONS_DIR
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash


@pytest_asyncio.fixture
async def db_handler() -> AsyncGenerator[DefaultPersistenceHandler, None]:
    """提供一个使用内存数据库并应用了迁移的持久化处理器实例。"""
    handler = DefaultPersistenceHandler(db_path=":memory:")
    await handler.connect()

    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql_script = migration_file.read_text("utf-8")
        await handler.connection.executescript(sql_script)

    await handler.connection.commit()
    yield handler
    await handler.close()


@pytest.mark.asyncio
async def test_ensure_pending_translations(db_handler: DefaultPersistenceHandler):
    """测试 ensure_pending_translations 能否正确创建内容和翻译任务。"""
    await db_handler.ensure_pending_translations(
        text_content="Hello World",
        target_langs=["de", "fr"],
        source_lang="en",
        engine_version="1.0",
        business_id="test.hello",
        context_hash="global",
    )
    async with db_handler.connection.execute(
        "SELECT COUNT(*) FROM th_content WHERE value = 'Hello World'"
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1

    async with db_handler.connection.execute(
        "SELECT lang_code, status FROM th_translations"
    ) as cursor:
        # --- 核心修正：显式转换为 list ---
        rows = list(await cursor.fetchall())
        assert len(rows) == 2
        statuses = {row["lang_code"]: row["status"] for row in rows}
        assert statuses["de"] == TranslationStatus.PENDING.value
        assert statuses["fr"] == TranslationStatus.PENDING.value


@pytest.mark.asyncio
async def test_stream_translatable_items(db_handler: DefaultPersistenceHandler):
    """测试流式获取任务，并验证状态是否正确更新为 TRANSLATING。"""
    # --- 核心修正：为所有调用提供 context_hash ---
    await db_handler.ensure_pending_translations(
        "Item 1", ["de"], "en", "1.0", business_id="item1", context_hash="hash1"
    )
    await db_handler.ensure_pending_translations(
        "Item 2", ["de"], "en", "1.0", business_id="item2", context_hash="hash1"
    )
    await db_handler.ensure_pending_translations(
        "Item 3", ["fr"], "en", "1.0", business_id="item3", context_hash="hash2"
    )

    items_stream = db_handler.stream_translatable_items(
        lang_code="de", statuses=[TranslationStatus.PENDING], batch_size=5
    )

    batch = []
    async for item_batch in items_stream:
        batch = item_batch
        break  # 只取第一个批次

    assert len(batch) == 2
    assert {item.value for item in batch} == {"Item 1", "Item 2"}

    async with db_handler.connection.execute(
        "SELECT status FROM th_translations WHERE lang_code = 'de'"
    ) as cursor:
        rows = await cursor.fetchall()
        assert all(row[0] == TranslationStatus.TRANSLATING.value for row in rows)


@pytest.mark.asyncio
async def test_save_and_get_translation(db_handler: DefaultPersistenceHandler):
    """测试保存翻译结果并能通过 get_translation 成功获取。"""
    context = {"some": "data"}
    context_hash = get_context_hash(context)

    await db_handler.ensure_pending_translations(
        "Hello",
        ["de"],
        "en",
        "1.0",
        "test.hello",
        context_hash,
        context_json='{"some": "data"}',
    )
    items_stream = db_handler.stream_translatable_items(
        "de", [TranslationStatus.PENDING], 5
    )
    batch = []
    async for item_batch in items_stream:
        batch = item_batch
        break
    assert batch
    item = batch[0]
    result = TranslationResult(
        original_content=item.value,
        translated_content="Hallo",
        target_lang="de",
        status=TranslationStatus.TRANSLATED,
        engine="debug",
        from_cache=False,
        business_id="test.hello",
        context_hash=context_hash,
    )
    await db_handler.save_translations([result])
    retrieved = await db_handler.get_translation("Hello", "de", context=context)
    assert retrieved is not None
    assert retrieved.translated_content == "Hallo"


@pytest.mark.asyncio
async def test_move_to_dlq(db_handler: DefaultPersistenceHandler):
    """测试将任务移至死信队列后，原任务被删除。"""
    await db_handler.ensure_pending_translations(
        "Fail Permanently", ["de"], "en", "1.0", context_hash="fail_hash"
    )
    item_to_fail = ContentItem(
        content_id=1, value="Fail Permanently", context_hash="fail_hash", context={}
    )
    await db_handler.move_to_dlq(
        item=item_to_fail,
        error_message="Max retries",
        engine_name="debug",
        engine_version="1.0",
    )
    async with db_handler.connection.execute(
        "SELECT COUNT(*) FROM th_translations WHERE content_id=1"
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 0
    async with db_handler.connection.execute(
        "SELECT COUNT(*) FROM th_dead_letter_queue"
    ) as cursor:
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1
