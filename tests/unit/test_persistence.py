# tests/unit/test_persistence.py
"""
针对 `trans_hub.persistence` 模块的单元测试。
v3.0.0 更新：全面重写以测试基于新 Schema 和协议的持久层实现。
"""

from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from aiosqlite import Row

from trans_hub.db.schema_manager import MIGRATIONS_DIR
from trans_hub.persistence.sqlite import SQLitePersistenceHandler
from trans_hub.utils import get_context_hash


@pytest_asyncio.fixture
async def db_handler() -> AsyncGenerator[SQLitePersistenceHandler, None]:
    """提供一个使用内存数据库并应用了 v3.0 schema 的 SQLitePersistenceHandler。"""
    handler = SQLitePersistenceHandler(db_path=":memory:")
    await handler.connect()

    initial_schema_path = MIGRATIONS_DIR / "001_initial.sql"
    sql_script = initial_schema_path.read_text("utf-8")

    await handler.connection.executescript(sql_script)
    await handler.connection.commit()

    yield handler

    await handler.close()


@pytest.mark.asyncio
async def test_ensure_content_and_context_creates_all_entities(
    db_handler: SQLitePersistenceHandler,
) -> None:
    """测试 ensure_content_and_context 是否能正确创建内容、上下文和任务实体。"""
    business_id = "test.hello.world"
    source_payload = {"text": "Hello World", "version": 1}
    context = {"domain": "testing"}
    target_langs = ["de", "fr"]
    engine_version = "3.0.0"

    with patch("trans_hub.persistence.sqlite.generate_uuid") as mock_uuid:
        mock_uuid.side_effect = [
            "uuid-content-1",
            "uuid-context-1",
            "uuid-job-1",
            "uuid-trans-de",
            "uuid-trans-fr",
        ]

        content_id, context_id = await db_handler.ensure_content_and_context(
            business_id=business_id,
            source_payload=source_payload,
            context=context,
        )
        await db_handler.create_pending_translations(
            content_id=content_id,
            context_id=context_id,
            target_langs=target_langs,
            source_lang="en",
            engine_version=engine_version,
            force_retranslate=False,
        )

    assert content_id == "uuid-content-1"
    assert context_id == "uuid-context-1"

    async with db_handler.connection.cursor() as cursor:
        # [核心修复] aiosqlite 的类型存根不够精确，row_factory 期望一个 Callable。
        # Row 本身是可调用的，但 mypy 无法推断出来。我们忽略这个错误。
        cursor.row_factory = Row

        await cursor.execute(
            "SELECT * FROM th_content WHERE business_id = ?", (business_id,)
        )
        content_row = await cursor.fetchone()
        assert content_row is not None
        assert content_row["id"] == "uuid-content-1"

        context_hash = get_context_hash(context)
        await cursor.execute(
            "SELECT * FROM th_contexts WHERE context_hash = ?", (context_hash,)
        )
        context_row = await cursor.fetchone()
        assert context_row is not None
        assert context_row["id"] == "uuid-context-1"

        await cursor.execute(
            "SELECT * FROM th_jobs WHERE content_id = ?", (content_id,)
        )
        job_row = await cursor.fetchone()
        assert job_row is not None
        assert job_row["id"] == "uuid-job-1"

        await cursor.execute(
            "SELECT COUNT(*) FROM th_translations WHERE content_id = ?", (content_id,)
        )
        count_row = await cursor.fetchone()
        assert count_row is not None
        assert count_row[0] == 2
