# tests/integration/test_persistence_postgres.py
"""
针对 `trans_hub.persistence.postgres` 的集成测试。

这些测试需要在 .env 文件或环境变量中将 TH_DATABASE_URL 设置为
一个可用的 PostgreSQL 连接字符串来运行。
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import TranslationStatus
from tests.integration.conftest import requires_postgres

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
async def test_pg_garbage_collect_cleans_up_old_data_correctly(
    postgres_handler: PersistenceHandler,
) -> None:
    """测试 garbage_collect 能否正确清理一个完整的孤立内容生命周期。"""
    # 1. 设置
    stale_bid = "test.pg.stale_item"
    fresh_bid = "test.pg.fresh_item"
    two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)

    # 创建 stale 和 fresh content, job, translation
    stale_content_id, _ = await postgres_handler.ensure_content_and_context(
        stale_bid, {"text": "stale"}, None
    )
    await postgres_handler.create_pending_translations(
        stale_content_id, None, ["de"], "en", "1.0"
    )

    fresh_content_id, _ = await postgres_handler.ensure_content_and_context(
        fresh_bid, {"text": "fresh"}, None
    )

    PostgresHandlerImpl = __import__("trans_hub.persistence.postgres").persistence.postgres.PostgresPersistenceHandler
    if isinstance(postgres_handler, PostgresHandlerImpl):
        async with postgres_handler._pool.acquire() as conn:
            # 手动将 stale job 的时间戳设为过期
            await conn.execute(
                "UPDATE th_jobs SET last_requested_at = $1 WHERE content_id = $2",
                two_days_ago, stale_content_id
            )

    # 2. 第一次 GC: 删除过期的 job
    report1 = await postgres_handler.garbage_collect(retention_days=1, dry_run=False)
    assert report1["deleted_jobs"] == 1
    # 此时 stale_content 因为还有 translation 关联，不应被删除
    assert report1["deleted_content"] == 0

    # 3. 手动删除 stale_content 的关联翻译，使其彻底孤立
    if isinstance(postgres_handler, PostgresHandlerImpl):
        async with postgres_handler._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM th_translations WHERE content_id = $1", stale_content_id
            )

    # 4. 第二次 GC: 删除已彻底孤立的 content
    report2 = await postgres_handler.garbage_collect(retention_days=1, dry_run=False)
    assert report2["deleted_content"] == 1

    # 5. 最终验证
    if isinstance(postgres_handler, PostgresHandlerImpl):
        async with postgres_handler._pool.acquire() as conn:
            stale_content = await conn.fetchrow(
                "SELECT 1 FROM th_content WHERE id = $1", stale_content_id
            )
            fresh_content = await conn.fetchrow(
                "SELECT 1 FROM th_content WHERE id = $1", fresh_content_id
            )
            assert stale_content is None
            assert fresh_content is not None


@pytest.mark.asyncio
async def test_pg_garbage_collect_respects_date_boundary(
    postgres_handler: PersistenceHandler,
) -> None:
    """为 PostgreSQL 精确测试垃圾回收（GC）的日期边界条件。"""
    retention_days = 2
    now_for_test = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    
    stale_bid = "pg.item.stale"
    stale_timestamp = now_for_test - timedelta(days=retention_days + 1)

    fresh_bid = "pg.item.fresh"
    fresh_timestamp = now_for_test - timedelta(days=retention_days)

    # 第一步：创建所有数据
    for bid in [stale_bid, fresh_bid]:
        await postgres_handler.ensure_content_and_context(
            business_id=bid,
            source_payload={"text": bid},
            context=None,
        )

    # 第二步：手动更新时间戳
    PostgresHandlerImpl = __import__("trans_hub.persistence.postgres").persistence.postgres.PostgresPersistenceHandler
    assert isinstance(postgres_handler, PostgresHandlerImpl)
    async with postgres_handler._pool.acquire() as conn:
        await conn.execute(
            "UPDATE th_jobs SET last_requested_at = $1 WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = $2)",
            stale_timestamp, stale_bid
        )
        await conn.execute(
            "UPDATE th_jobs SET last_requested_at = $1 WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = $2)",
            fresh_timestamp, fresh_bid
        )

    # WHEN: 运行垃圾回收，并注入确定的 "now" 时间
    report = await postgres_handler.garbage_collect(
        retention_days=retention_days, dry_run=False, _now=now_for_test
    )

    # THEN: 验证只有过期的任务被删除
    assert report.get("deleted_jobs", 0) == 1
    
    # 验证数据库状态
    async with postgres_handler._pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM th_jobs")
        assert count == 1
        
        remaining_bid = await conn.fetchval(
            "SELECT c.business_id FROM th_jobs j JOIN th_content c ON j.content_id = c.id"
        )
        assert remaining_bid == fresh_bid


@pytest.mark.asyncio
async def test_pg_listen_notify_workflow(postgres_handler: PersistenceHandler) -> None:
    """测试 PostgreSQL 的 LISTEN/NOTIFY 事件驱动机制。"""
    notification_future: asyncio.Future[str] = asyncio.Future()

    async def listener_task() -> None:
        try:
            async for payload in postgres_handler.listen_for_notifications():
                notification_future.set_result(payload)
                break
        except Exception as e:
            if not notification_future.done():
                notification_future.set_exception(e)

    task = asyncio.create_task(listener_task())

    await asyncio.sleep(0.1)
    assert not notification_future.done()

    business_id = "test.pg.notify"
    content_id, _ = await postgres_handler.ensure_content_and_context(
        business_id, {"text": "notify me"}, None
    )
    await postgres_handler.create_pending_translations(
        content_id, None, ["de"], "en", "1.0"
    )

    try:
        received_payload = await asyncio.wait_for(notification_future, timeout=2.0)
        assert received_payload is not None
        from uuid import UUID
        assert isinstance(UUID(received_payload), UUID)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)