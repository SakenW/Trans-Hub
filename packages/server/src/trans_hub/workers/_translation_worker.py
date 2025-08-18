# packages/server/src/trans_hub/workers/_translation_worker.py
"""
负责处理后台翻译任务的 Worker (UoW 架构版)。
"""

import asyncio
import signal
from typing import Any

import structlog

from trans_hub.application.processors import TranslationProcessor
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.engines.base import BaseTranslationEngine
from trans_hub.infrastructure.engines.factory import create_engine_instance
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.exceptions import TransHubError

logger = structlog.get_logger(__name__)


async def run_once(
    uow_factory: UowFactory,
    processor: TranslationProcessor,
    active_engine: BaseTranslationEngine[Any],
    batch_size: int,
) -> None:
    """
    执行一轮 Worker 的核心处理逻辑。
    它现在使用 UoW 来确保拉取和处理任务的原子性。
    """
    tasks_processed = 0
    try:
        # Worker 的核心逻辑现在在一个独立的 UoW 中运行
        async with uow_factory() as uow:
            # 使用流式处理，但在同一个 session 中
            # 注意：这里的 stream_drafts 内部使用了 FOR UPDATE SKIP LOCKED
            # 它将在事务提交前一直持有行锁
            async for batch in uow.translations.stream_drafts(batch_size):
                if not batch:
                    continue

                logger.info("获取到新一批翻译任务，正在处理...", count=len(batch))

                # 处理器现在也接收 UoW 实例，以便在同一个事务中执行更新
                await processor.process_batch(uow, batch, active_engine)
                tasks_processed += len(batch)

        if tasks_processed > 0:
            logger.info("本轮任务处理完成。", total_processed=tasks_processed)
        else:
            logger.debug("本轮未发现需要处理的任务。")

    except Exception as e:
        logger.error("处理任务批次时发生未知错误。", error=e, exc_info=True)


async def run_worker_loop(
    config: TransHubConfig, uow_factory: UowFactory, shutdown_event: asyncio.Event
):
    """Worker 的主循环，现在直接依赖 UoW 工厂。"""
    active_engine: BaseTranslationEngine[Any] | None = None

    def _signal_handler(*args: Any):
        logger.warning("收到停机信号，正在准备优雅关闭...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        # 在循环外创建一次引擎实例和处理器
        try:
            active_engine = create_engine_instance(config, config.active_engine)
            await active_engine.initialize()

            # 处理器现在也在这里初始化，但它不再持有状态
            # stream_producer 暂时为 None，等待 Outbox 模式实现
            processor = TranslationProcessor(stream_producer=None, event_stream_name="")

            logger.info("翻译 Worker 已启动，正在轮询任务...")
        except TransHubError as e:
            logger.error(
                "无法初始化激活的翻译引擎，Worker 将退出。",
                engine=config.active_engine,
                error=e,
            )
            return

        while not shutdown_event.is_set():
            await run_once(
                uow_factory=uow_factory,
                processor=processor,
                active_engine=active_engine,
                batch_size=config.batch_size,
            )
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=config.worker.poll_interval
                )
            except asyncio.TimeoutError:
                pass

    except asyncio.CancelledError:
        logger.info("Worker 循环被取消。")
    finally:
        logger.info("Worker 正在关闭...")
        if active_engine:
            await active_engine.close()
        logger.info("Worker 已安全关闭。")
