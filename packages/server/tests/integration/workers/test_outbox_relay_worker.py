# tests/integration/workers/test_outbox_relay_worker.py
"""
对 Outbox Relay Worker 的核心流程进行集成测试。
"""

import pytest
from sqlalchemy import select
from trans_hub.infrastructure.db._schema import ThOutboxEvents
from trans_hub.infrastructure.uow import UowFactory
from trans_hub.workers import _outbox_relay_worker

from tests.helpers.tools.fakes import FakeStreamProducer

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_outbox_relay_worker_run_once_processes_pending_events(
    uow_factory: UowFactory,
):
    """
    验证 Outbox Relay Worker 的 `run_once` 函数能否成功处理待处理事件，
    将其发布到外部流，并更新数据库中的状态。
    """
    # --- 1. 准备: 在数据库中手动创建待处理事件 ---
    project_id = "outbox-proj"
    topic = "test_events"
    event_payload_1 = {"id": "1", "data": "event1"}
    event_payload_2 = {"id": "2", "data": "event2"}

    async with uow_factory() as uow:
        # 使用仓库添加入口
        await uow.outbox.add(
            project_id=project_id, event_id="evt1", topic=topic, payload=event_payload_1
        )
        await uow.outbox.add(
            project_id=project_id, event_id="evt2", topic=topic, payload=event_payload_2
        )

    # --- 2. 准备 Worker 的依赖 ---
    fake_producer = FakeStreamProducer()

    # --- 3. 执行: 调用 worker 的核心处理逻辑 ---
    await _outbox_relay_worker.run_once(
        uow_factory=uow_factory,
        stream_producer=fake_producer,
        batch_size=10,
    )

    # --- 4. 验证 ---
    # 4a. 验证事件是否已发布到模拟的 Stream Producer
    assert fake_producer.call_count == 2
    assert len(fake_producer.published_events[topic]) == 2
    published_ids = {p["id"] for p in fake_producer.published_events[topic]}
    assert published_ids == {"1", "2"}

    # 4b. 在新的 UoW 中验证数据库状态
    async with uow_factory() as uow:
        stmt = select(ThOutboxEvents).where(ThOutboxEvents.project_id == project_id)
        results = (await uow.session.execute(stmt)).scalars().all()

        assert len(results) == 2, "所有事件应保留在数据库中"
        for event in results:
            assert event.status == "published", "事件状态应更新为 'published'"
            assert event.published_at is not None, "应记录发布时间"


@pytest.mark.asyncio
async def test_outbox_relay_worker_run_once_handles_no_events(
    uow_factory: UowFactory,
):
    """验证当没有待处理事件时，worker 不会执行任何操作。"""
    fake_producer = FakeStreamProducer()

    await _outbox_relay_worker.run_once(
        uow_factory=uow_factory, stream_producer=fake_producer
    )

    assert fake_producer.call_count == 0, "不应有任何事件被发布"
