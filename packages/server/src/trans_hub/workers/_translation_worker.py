# packages/server/src/trans_hub/workers/_translation_worker.py
import asyncio
import signal
from typing import Any

import structlog
from trans_hub.application.processors import TranslationProcessor
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.engines.base import BaseTranslationEngine
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.exceptions import TransHubError

logger = structlog.get_logger(__name__)


class TranslationWorker:
    """
    [DI 重构] 负责处理后台翻译任务的 Worker 类。
    所有依赖项通过构造函数注入。
    """

    def __init__(
        self,
        config: TransHubConfig,
        uow_factory: UowFactory,
        processor: TranslationProcessor,
        active_engine: BaseTranslationEngine[Any],
    ):
        self._config = config
        self._uow_factory = uow_factory
        self._processor = processor
        self._active_engine = active_engine

    async def run_once(self) -> None:
        """
        执行一轮 Worker 的核心处理逻辑。
        """
        tasks_processed = 0
        try:
            async with self._uow_factory() as uow:
                async for batch in uow.translations.stream_drafts(
                    self._config.batch_size
                ):
                    if not batch:
                        continue

                    logger.info("获取到新一批翻译任务，正在处理...", count=len(batch))
                    await self._processor.process_batch(uow, batch, self._active_engine)
                    tasks_processed += len(batch)

            if tasks_processed > 0:
                logger.info("本轮任务处理完成。", total_processed=tasks_processed)
            else:
                logger.debug("本轮未发现需要处理的任务。")

        except Exception as e:
            logger.error("处理任务批次时发生未知错误。", error=e, exc_info=True)

    async def run_loop(self, shutdown_event: asyncio.Event):
        """Worker 的主循环。"""

        def _signal_handler(*args: Any):
            logger.warning("收到停机信号，正在准备优雅关闭 (TranslationWorker)...")
            shutdown_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        try:
            await self._active_engine.initialize()
            logger.info("翻译 Worker 已启动，正在轮询任务...")

            while not shutdown_event.is_set():
                await self.run_once()
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=self._config.worker.poll_interval
                    )
                except asyncio.TimeoutError:
                    pass

        except TransHubError as e:
            logger.error(
                "无法初始化激活的翻译引擎，Worker 将退出。",
                engine=self._config.active_engine,
                error=e,
            )
        except asyncio.CancelledError:
            logger.info("翻译 Worker 循环被取消。")
        finally:
            logger.info("翻译 Worker 正在关闭...")
            await self._active_engine.close()
            logger.info("翻译 Worker 已安全关闭。")
