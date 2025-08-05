# trans_hub/cli/worker.py
"""
处理后台 Worker 运行的 CLI 命令。
v3.0.0 更新：调整日志输出以适配结构化载荷（payload）。
"""

import asyncio
import signal
from typing import Any

import structlog
import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator
from trans_hub.utils import validate_lang_codes

logger = structlog.get_logger(__name__)
console = Console()
worker_app = typer.Typer(help="启动后台翻译 Worker")


async def consume_all(coordinator: Coordinator, lang: str, reason: str) -> int:
    """消费指定语言的所有待办任务并返回处理数量。"""
    processed_count = 0
    logger.info(f"开始处理任务 ({reason})...")
    # v3.20 修复：`process_pending_translations` 现在是一个同步方法，返回一个异步生成器
    # 我们需要在 `async for` 中直接使用它。
    async for result in coordinator.process_pending_translations(lang):
        processed_count += 1
        original_text = result.original_payload.get(
            "text", str(result.original_payload)
        )
        logger.info(
            "处理完成",
            lang=lang,
            business_id=result.business_id,
            status=result.status.value,
            original=f"'{str(original_text)[:20]}...'",
            error=result.error,
        )
    if processed_count > 0:
        logger.info(f"本轮处理完成，共处理 {processed_count} 个任务。")
    return processed_count


async def polling_loop(
    coordinator: Coordinator, lang: str, shutdown_event: asyncio.Event
) -> None:
    """传统的基于 sleep 的轮询循环。"""
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(coordinator.config.worker_poll_interval)
            await consume_all(coordinator, lang, f"轮询检查 ({lang})")
        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("轮询循环中发生未知错误", lang=lang, exc_info=True)


async def notification_loop(
    coordinator: Coordinator, lang: str, shutdown_event: asyncio.Event
) -> None:
    """基于 LISTEN/NOTIFY 的事件驱动循环。"""
    # v3.20 修复：`listen_for_notifications` 是一个同步方法，返回异步生成器
    notification_generator = coordinator.handler.listen_for_notifications()
    logger.info("正在等待新任务通知...", lang=lang)
    while not shutdown_event.is_set():
        try:
            notification_task = asyncio.create_task(notification_generator.__anext__())
            shutdown_task = asyncio.create_task(shutdown_event.wait())
            done, pending = await asyncio.wait(
                [notification_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()

            if shutdown_task in done:
                break

            if notification_task in done:
                payload = notification_task.result()
                logger.info("收到新任务通知!", payload=payload, lang=lang)
                await consume_all(coordinator, lang, f"收到通知后处理 ({lang})")
                logger.info("正在等待下一次新任务通知...", lang=lang)

        except asyncio.CancelledError:
            break
        except StopAsyncIteration:
            logger.warning("通知生成器已停止，Worker 将退出。")
            break
        except Exception:
            logger.error("通知循环中发生未知错误", lang=lang, exc_info=True)


async def _run_worker_loop(
    coordinator: Coordinator, shutdown_event: asyncio.Event, target_langs: list[str]
) -> None:
    """Worker 的主循环，包含信号处理和优雅停机逻辑。"""
    loop = asyncio.get_running_loop()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.warning(
            "收到停机信号，正在准备优雅关闭...", signal=signal.strsignal(signum)
        )
        if not shutdown_event.is_set():
            loop.call_soon_threadsafe(shutdown_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler, sig, None)

    use_notifications = coordinator.handler.SUPPORTS_NOTIFICATIONS
    mode = "事件驱动" if use_notifications else "轮询"
    console.print(
        f"▶️  [bold green]Worker 已启动 ({mode}模式)[/bold green]，正在处理语言: "
        f"[cyan]{', '.join(target_langs)}[/cyan]. 按 CTRL+C 停止。"
    )

    async def process_language(lang: str) -> None:
        await consume_all(coordinator, lang, f"启动时检查积压任务 ({lang})")

        if not use_notifications:
            await polling_loop(coordinator, lang, shutdown_event)
            return

        await notification_loop(coordinator, lang, shutdown_event)

    worker_tasks = [
        asyncio.create_task(process_language(lang)) for lang in target_langs
    ]
    for task in worker_tasks:
        coordinator.track_task(task)

    await shutdown_event.wait()


@worker_app.command("start")
def worker_start(
    ctx: typer.Context,
    target_langs: list[str] = typer.Option(
        ..., "--lang", "-l", help="一个或多个要处理的目标语言代码。"
    ),
) -> None:
    """
    启动一个或多个后台 Worker 进程，持续处理待翻译任务。
    """
    try:
        validate_lang_codes(target_langs)
    except ValueError as e:
        console.print(f"[bold red]❌ 语言代码错误: {e}[/bold red]")
        raise typer.Exit(code=1)

    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    shutdown_event = asyncio.Event()

    async def main_async_loop() -> None:
        try:
            await coordinator.initialize()
            await _run_worker_loop(coordinator, shutdown_event, target_langs)
        finally:
            console.print("\n[yellow]Worker 正在关闭，请稍候...[/yellow]")
            await coordinator.close()
            console.print("[bold]✅ Worker 已安全关闭。[/bold]")

    try:
        asyncio.run(main_async_loop())
    except KeyboardInterrupt:
        logger.info("主循环被强制中断。")
