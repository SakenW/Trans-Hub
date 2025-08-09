# trans_hub/cli/worker.py
"""处理后台 Worker 运行的 CLI 命令 (UIDA 架构版)。"""
import asyncio
import signal
from typing import Annotated, Any

import structlog
import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator
from trans_hub.core import TranslationStatus

logger = structlog.get_logger(__name__)
console = Console()
worker_app = typer.Typer(help="启动后台翻译 Worker (UIDA 模式)")


async def consume_and_process(coordinator: Coordinator, reason: str) -> int:
    """
    消费并处理所有待办的翻译任务。
    这是一个完整的“拉取-处理”循环。
    """
    processed_count = 0
    logger.info(f"开始处理翻译任务 ({reason})...")

    # Worker 现在处理所有语言的 'draft' 状态任务
    # 注意: 为了简单起见，我们先从一个通用队列拉取，未来可以按语言或项目分片
    pending_statuses = [TranslationStatus.DRAFT]
    
    # 获取活动的翻译引擎实例
    active_engine = coordinator._get_or_create_engine_instance(
        coordinator.config.active_engine.value
    )
    if not active_engine.initialized:
        await active_engine.initialize()

    # 流式获取待处理项
    async for batch in coordinator.handler.stream_translatable_items(
        # lang_code 和 statuses 参数需要根据新的持久化接口进行适配
        # 假设 stream_translatable_items 能够获取所有待处理任务
        lang_code="*", # 示意，表示所有语言
        statuses=pending_statuses,
        batch_size=coordinator.config.batch_size,
    ):
        if not batch:
            continue
        
        batch_size = len(batch)
        processed_count += batch_size
        logger.info(f"获取到 {batch_size} 个任务进行处理...", first_id=batch[0].translation_id)
        
        # 将批次交给处理策略
        results = await coordinator.processing_policy.process_batch(
            batch, coordinator.processing_context, active_engine
        )

        # 记录处理结果
        for res in results:
            if res.status == TranslationStatus.FAILED:
                logger.error("任务处理失败", translation_id=res.translation_id, error=res.error)
            else:
                logger.info("任务处理成功", translation_id=res.translation_id, new_status=res.status.value)

    if processed_count > 0:
        logger.info(f"本轮处理完成，共处理 {processed_count} 个任务。")
    return processed_count


async def polling_loop(coordinator: Coordinator, shutdown_event: asyncio.Event) -> None:
    """传统的基于 sleep 的轮询循环。"""
    while not shutdown_event.is_set():
        try:
            await consume_and_process(coordinator, "轮询检查")
            await asyncio.sleep(coordinator.config.worker_poll_interval)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("轮询循环中发生未知错误", exc_info=True)
            await asyncio.sleep(coordinator.config.worker_poll_interval * 2) # 发生错误时延长等待


async def notification_loop(coordinator: Coordinator, shutdown_event: asyncio.Event) -> None:
    """基于 LISTEN/NOTIFY 的事件驱动循环。"""
    notification_generator = coordinator.handler.listen_for_notifications()
    logger.info("正在等待新任务通知...")
    while not shutdown_event.is_set():
        try:
            notification_task = asyncio.create_task(notification_generator.__anext__())
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            done, pending = await asyncio.wait(
                [notification_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if notification_task in done:
                try:
                    payload = notification_task.result()
                    logger.info("收到新任务通知!", payload=payload)
                    await consume_and_process(coordinator, "收到通知后处理")
                    logger.info("正在等待下一次新任务通知...")
                except (StopAsyncIteration, asyncio.CancelledError):
                    break
                except Exception:
                    logger.error("通知生成器或任务处理中发生错误", exc_info=True)
                    shutdown_event.set() # 发生严重错误时触发停机
            
            if shutdown_task in done:
                break
        except asyncio.CancelledError:
            break

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

    # 启动时先处理一次积压任务
    await consume_and_process(coordinator, "启动时检查积压任务")
    
    # 根据数据库能力选择主循环模式
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