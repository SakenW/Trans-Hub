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

logger = structlog.get_logger(__name__)

async def run_worker_loop(config: TransHubConfig, shutdown_event: asyncio.Event):
    """Worker 的主循环，包含优雅停机逻辑。"""
    coordinator = Coordinator(config)
    
    def _signal_handler(*args: Any):
        logger.warning("收到停机信号，正在准备优雅关闭...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await coordinator.initialize()
        logger.info("翻译 Worker 已启动，正在等待任务...")
        
        while not shutdown_event.is_set():
            try:
                # 真实的实现会从 Redis Queue 或 DB 轮询中获取任务
                # 这里我们用 sleep 模拟轮询
                await asyncio.wait_for(shutdown_event.wait(), timeout=config.worker.poll_interval)
            except asyncio.TimeoutError:
                # 在这里执行一次轮询检查
                logger.debug("Worker 正在轮询检查新任务...")
                # await run_once(coordinator)
                pass

    except asyncio.CancelledError:
        logger.info("Worker 循环被取消。")
    finally:
        logger.info("Worker 正在关闭...")
        await coordinator.close()
        logger.info("Worker 已安全关闭。")

# ... (run_once 等辅助函数可以放在这里) ...