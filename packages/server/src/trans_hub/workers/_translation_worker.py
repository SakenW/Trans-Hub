# packages/server/src/trans_hub/workers/_translation_worker.py
"""
负责处理后台翻译任务的 Worker。
"""

import asyncio
import signal
from typing import Any

import structlog
from trans_hub.application.coordinator import Coordinator
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.engines.base import BaseTranslationEngine
from trans_hub.infrastructure.engines.factory import create_engine_instance
from trans_hub_core.exceptions import TransHubError

logger = structlog.get_logger(__name__)


async def run_once(coordinator: Coordinator, active_engine: BaseTranslationEngine[Any]) -> None:
    """
    [修复] 执行一轮 Worker 的核心处理逻辑。

    此函数现在接收一个已初始化的 `active_engine`，而不是自己创建。
    这确保了引擎的生命周期和异步上下文由调用方统一管理，避免了事件循环冲突。
    """
    try:
        batch_size = coordinator.config.batch_size
        tasks_processed = 0
        async for batch in coordinator.handler.stream_draft_translations(batch_size):
            if not batch:
                continue
            
            logger.info("获取到新一批翻译任务，正在处理...", count=len(batch))
            if coordinator.processor:
                await coordinator.processor.process_batch(batch, active_engine)
                tasks_processed += len(batch)
            else:
                logger.error("处理器未初始化，无法处理任务。")
                break # 出现严重问题，退出循环
        
        if tasks_processed > 0:
            logger.info("本轮任务处理完成。", total_processed=tasks_processed)
        else:
            logger.debug("本轮未发现需要处理的任务。")

    except Exception as e:
        logger.error("处理任务批次时发生未知错误。", error=e, exc_info=True)


async def run_worker_loop(config: TransHubConfig, shutdown_event: asyncio.Event):
    """[修复] Worker 的主循环，现在正确管理引擎的生命周期。"""
    coordinator = Coordinator(config)
    active_engine: BaseTranslationEngine[Any] | None = None

    def _signal_handler(*args: Any):
        logger.warning("收到停机信号，正在准备优雅关闭...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await coordinator.initialize()

        # 在循环外创建一次引擎实例
        try:
            active_engine = create_engine_instance(
                coordinator.config, coordinator.config.active_engine
            )
            await active_engine.initialize()
            logger.info("翻译 Worker 已启动，正在轮询任务...")
        except TransHubError as e:
            logger.error(
                "无法初始化激活的翻译引擎，Worker 将退出。",
                engine=coordinator.config.active_engine,
                error=e,
            )
            return

        while not shutdown_event.is_set():
            await run_once(coordinator, active_engine)
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
        await coordinator.close()
        logger.info("Worker 已安全关闭。")