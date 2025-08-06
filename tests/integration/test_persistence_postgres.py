# tests/integration/test_persistence_postgres.py
"""
针对 `trans_hub.persistence.postgres` 的集成测试。

这些测试需要在 .env 文件或环境变量中将 TH_DATABASE_URL 设置为
一个可用的 PostgreSQL 连接字符串来运行。
"""

from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.conftest import requires_postgres
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import TranslationStatus

# 将标记应用到整个模块的所有测试
pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_pg_ensure_content_and_context_creates_all_entities(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试 ensure_content_and_context 是否能正确创建所有实体。"""
    business_id = "test.pg.hello"
    source_payload = {"text": "Hello PG"}
    context = {"domain": "testing"}

    content_id, context_id = await postgres_handler.ensure_content_and_context(
        business_id=business_id,
        source_payload=source_payload,
        context=context,
    )
    assert content_id is not None
    assert context_id is not None

    source_payload_updated = {"text": "Hello PG Updated"}
    content_id2, context_id2 = await postgres_handler.ensure_content_and_context(
        business_id=business_id,
        source_payload=source_payload_updated,
        context=context,
    )
    assert content_id == content_id2
    assert context_id == context_id2


@pytest.mark.asyncio
async def test_pg_stream_translatable_items_fetches_and_updates_status(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试 stream_translatable_items 能否正确获取 PENDING 任务并将其状态更新为 TRANSLATING。"""
    business_id = "test.pg.stream"
    content_id, _ = await postgres_handler.ensure_content_and_context(
        business_id, {"text": "stream me"}, None
    )
    target_langs = ["de", "fr", "es"]
    await postgres_handler.create_pending_translations(
        content_id, None, target_langs, "en", "1.0"
    )

    stream_de = postgres_handler.stream_translatable_items(
        "de", [TranslationStatus.PENDING], batch_size=2
    )
    items_de = [item async for batch in stream_de for item in batch]

    assert len(items_de) == 1
    assert items_de[0].business_id == business_id

    res_de = await postgres_handler.find_translation(business_id, "de")
    assert res_de and res_de.status == TranslationStatus.TRANSLATING

    res_es = await postgres_handler.find_translation(business_id, "es")
    assert res_es and res_es.status == TranslationStatus.PENDING


@pytest.mark.asyncio
async def test_pg_garbage_collect_workflow_and_date_boundary(
    postgres_handler: PersistenceHandler,
) -> None:
    """为 PostgreSQL 精确测试垃圾回收（GC）的日期边界和完整清理流程。"""
    # GIVEN: 准备测试数据和确定的时间
    retention_days = 2
    now_for_test = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)

    stale_bid = "pg.item.stale"
    # 此项刚好过期
    stale_timestamp = now_for_test - timedelta(days=retention_days, microseconds=1)

    fresh_bid = "pg.item.fresh"
    # 此项刚好未过期
    fresh_timestamp = now_for_test - timedelta(days=retention_days)

    # 步骤 1: 创建所有数据
    stale_content_id, _ = await postgres_handler.ensure_content_and_context(
        stale_bid, {"text": "stale"}, None
    )
    await postgres_handler.create_pending_translations(
        stale_content_id, None, ["de"], "en", "1.0"
    )
    fresh_content_id, _ = await postgres_handler.ensure_content_and_context(
        fresh_bid, {"text": "fresh"}, None
    )

    # 步骤 2: 手动更新时间戳
    postgres_handler_impl = __import__(
        "trans_hub.persistence.postgres"
    ).persistence.postgres.PostgresPersistenceHandler
    assert isinstance(postgres_handler, postgres_handler_impl)
    async with postgres_handler._pool.acquire() as conn:
        await conn.execute(
            "UPDATE th_jobs SET last_requested_at = $1 WHERE content_id = $2",
            stale_timestamp,
            stale_content_id,
        )
        await conn.execute(
            "UPDATE th_jobs SET last_requested_at = $1 WHERE content_id = $2",
            fresh_timestamp,
            fresh_content_id,
        )

    # WHEN: 运行第一次GC，应该只删除过期的 job
    report1 = await postgres_handler.garbage_collect(
        retention_days=retention_days, dry_run=False, _now=now_for_test
    )
    # THEN: 验证只有过期的 job 被删除
    assert report1["deleted_jobs"] == 1
    assert report1["deleted_content"] == 0

    # 步骤 3: 手动删除 stale_content 的关联翻译，使其彻底孤立
    async with postgres_handler._pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM th_translations WHERE content_id = $1", stale_content_id
        )

    # WHEN: 运行第二次GC，现在应该能删除孤立的 content
    report2 = await postgres_handler.garbage_collect(
        retention_days=retention_days, dry_run=False, _now=now_for_test
    )
    # THEN: 验证孤立的 content 被删除
    assert report2["deleted_content"] == 1

    # 最终验证
    async with postgres_handler._pool.acquire() as conn:
        stale_content = await conn.fetchrow(
            "SELECT 1 FROM th_content WHERE id = $1", stale_content_id
        )
        fresh_content = await conn.fetchrow(
            "SELECT 1 FROM th_content WHERE id = $1", fresh_content_id
        )
        assert stale_content is None
        assert fresh_content is not None
