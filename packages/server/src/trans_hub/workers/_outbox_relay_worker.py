# packages/server/src/trans_hub/workers/_outbox_relay_worker.py
"""
事务性发件箱中继 Worker。
负责将数据库中的待处理事件发布到外部消息系统（如 Redis Streams）。
"""

import asyncio
import signal
from typing import Any

import structlog

from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.interfaces import StreamProducer

logger = structlog.get_logger(__name__)


async def run_once(
    uow_factory: UowFactory,
    stream_producer: StreamProducer,
    batch_size: int = 100,
) -> None:
    """执行一轮 Outbox 中继的核心逻辑。"""
    events_published = 0
    try:
        async with uow_factory() as uow:
            pending_events = await uow.outbox.pull_pending(batch_size)
            if not pending_events:
                logger.debug("本轮未发现待处理的发件箱事件。")
                return

            logger.info(f"获取到 {len(pending_events)} 条待处理事件，正在发布...")

            publish_tasks = [
                stream_producer.publish(event.topic, event.payload)
                for event in pending_events
            ]
            results = await asyncio.gather(*publish_tasks, return_exceptions=True)

            # 处理发布结果，仅标记成功发布的事件
            successful_event_ids = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"事件发布失败: {pending_events[i].id}",
                        error=result,
                        event_topic=pending_events[i].topic,
                        exc_info=True
                    )
                else:
                    successful_event_ids.append(pending_events[i].id)

            # 仅标记成功发布的事件
            if successful_event_ids:
                await uow.outbox.mark_as_published(successful_event_ids)
                events_published = len(successful_event_ids)
                
                if len(successful_event_ids) < len(pending_events):
                    failed_count = len(pending_events) - len(successful_event_ids)
                    logger.warning(
                        f"部分事件发布失败: {failed_count}/{len(pending_events)} 失败，"
                        f"{len(successful_event_ids)} 成功发布"
                    )
            else:
                logger.error(f"所有 {len(pending_events)} 个事件发布均失败")
                events_published = 0

        logger.info(f"成功发布并标记了 {events_published} 条事件。")

    except Exception as e:
        logger.error("处理发件箱事件时发生未知错误。", error=e, exc_info=True)


async def run_relay_loop(
    config: TransHubConfig,
    uow_factory: UowFactory,
    stream_producer: StreamProducer,
    shutdown_event: asyncio.Event,
):
    """Outbox 中继 Worker 的主循环。"""

    def _signal_handler(*args: Any):
        logger.warning("收到停机信号，正在准备优雅关闭...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("Outbox 中继 Worker 已启动，正在轮询任务...")
    while not shutdown_event.is_set():
        await run_once(uow_factory, stream_producer)
        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=config.worker.poll_interval
            )
        except asyncio.TimeoutError:
            pass

    logger.info("Outbox 中继 Worker 已安全关闭。")
