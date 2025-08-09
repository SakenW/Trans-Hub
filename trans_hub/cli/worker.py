# trans_hub/cli/worker.py
"""处理后台 Worker 运行的 CLI 命令（白皮书 Final v1.2）。"""
import asyncio
import signal
from typing import Any

import structlog
import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator

logger = structlog.get_logger(__name__)
console = Console()
worker_app = typer.Typer(help="启动后台翻译 Worker")


async def consume_and_process(coordinator: Coordinator, reason: str) -> int:
    """
    消费并处理所有 'draft' 状态的翻译任务。
    这是一个完整的“拉取-处理”循环。
    """
    logger.info(f"开始处理翻译任务 ({reason})...")
    
    active_engine = coordinator._get_or_create_engine_instance(
        coordinator.config.active_engine.value
    )
    if not active_engine.initialized:
        await active_engine.initialize()

    total_processed = 0
    async for batch in coordinator.handler.stream_draft_translations(
        batch_size=coordinator.config.batch_size
    ):
        if not batch:
            continue
        
        batch_size = len(batch)
        total_processed += batch_size
        logger.info(f"获取到 {batch_size} 个草稿任务进行处理...", first_id=batch[0].translation_id)
        
        await coordinator.processing_policy.process_batch(
            batch, coordinator.processing_context, active_engine
        )

    if total_processed > 0:
        logger.info(f"本轮处理完成，共处理 {total_processed} 个任务。")
    return total_processed


async def polling_loop(coordinator: Coordinator, shutdown_event: asyncio.Event) -> None:
    """传统的基于 sleep 的轮询循环。"""
    while not shutdown_event.is_set():
        try:
            await consume_and_process(coordinator, "轮询检查")
            await asyncio.wait_for(shutdown_event.wait(), timeout=coordinator.config.worker_poll_interval)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("轮询循环中发生未知错误", exc_info=True)
            await asyncio.sleep(coordinator.config.worker_poll_interval * 2)

async def notification_loop(coordinator: Coordinator, shutdown_event: asyncio.Event) -> None:
    """基于 LISTEN/NOTIFY 的事件驱动循环。"""
    notification_generator = coordinator.handler.listen_for_notifications()
    logger.info("正在等待新任务通知...")
    while not shutdown_event.is_set():
        try:
            notification_task = asyncio.create_task(notification_generator.__anext__())
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            done, pending = await asyncio.wait(
                [notification_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending: task.cancel()

            if notification_task in done:
                await consume_and_process(coordinator, f"收到通知: {notification_task.result()}")
                logger.info("正在等待下一次新任务通知...")
            if shutdown_task in done:
                break
        except (StopAsyncIteration, asyncio.CancelledError):
            break
        except Exception:
            logger.error("通知循环或任务处理中发生错误", exc_info=True)
            shutdown_event.set()

async def _run_worker_loop(coordinator: Coordinator, shutdown_event: asyncio.Event) -> None:
    """Worker 的主循环，包含信号处理和优雅停机逻辑。"""
    loop = asyncio.get_running_loop()
    def _signal_handler(signum: int, frame: Any) -> None:
        logger.warning("收到停机信号，正在准备优雅关闭...", signal=signal.strsignal(signum))
        if not shutdown_event.is_set():
            loop.call_soon_threadsafe(shutdown_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler, sig, None)

    use_notifications = coordinator.handler.SUPPORTS_NOTIFICATIONS
    mode = "事件驱动" if use_notifications else "轮询"
    console.print(f"▶️  [bold green]Worker 已启动 ({mode}模式)[/bold green]. 按 CTRL+C 停止。")

    await consume_and_process(coordinator, "启动时检查积压任务")
    
    if use_notifications:
        await notification_loop(coordinator, shutdown_event)
    else:
        await polling_loop(coordinator, shutdown_event)


@worker_app.command("start")
def worker_start(ctx: typer.Context) -> None:
    """启动一个后台 Worker 进程，持续处理待翻译任务。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    shutdown_event = asyncio.Event()

    async def main_async_loop() -> None:
        try:
            await coordinator.initialize()
            await _run_worker_loop(coordinator, shutdown_event)
        finally:
            console.print("\n[yellow]Worker 正在关闭，请稍候...[/yellow]")
            await coordinator.close()
            console.print("[bold]✅ Worker 已安全关闭。[/bold]")

    try:
        asyncio.run(main_async_loop())
    except KeyboardInterrupt:
        logger.info("主循环被强制中断。")