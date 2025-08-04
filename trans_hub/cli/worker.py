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


async def _run_worker_loop(
    coordinator: Coordinator, shutdown_event: asyncio.Event, target_langs: list[str]
) -> None:
    """Worker 的主循环，包含信号处理和优雅停机逻辑。

    Args:
        coordinator: 已初始化的 Coordinator 实例。
        shutdown_event: 用于触发停机的 asyncio.Event。
        target_langs: 要处理的目标语言列表。
    """
    loop = asyncio.get_running_loop()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.warning(
            "收到停机信号，正在准备优雅关闭...", signal=signal.strsignal(signum)
        )
        if not shutdown_event.is_set():
            loop.call_soon_threadsafe(shutdown_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler, sig, None)

    console.print(
        "▶️  [bold green]Worker 已启动[/bold green]，正在处理语言: "
        f"[cyan]{', '.join(target_langs)}[/cyan]. 按 CTRL+C 停止。"
    )

    async def process_language(lang: str) -> None:
        while not shutdown_event.is_set():
            try:
                processed_count = 0
                async for result in coordinator.process_pending_translations(lang):
                    processed_count += 1
                    # 从 payload 中提取要记录的文本，这里我们约定使用 'text' 键
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
                if processed_count == 0:
                    try:
                        poll_interval = (
                            coordinator.config.logging.level.lower() == "debug"
                            and 5
                            or 10
                        )
                        await asyncio.wait_for(
                            shutdown_event.wait(), timeout=poll_interval
                        )
                    except asyncio.TimeoutError:
                        continue  # 正常轮询
            except Exception:
                logger.error(
                    "Worker 循环中发生未知错误，5秒后重试...", lang=lang, exc_info=True
                )
                await asyncio.sleep(5)

    worker_tasks = [
        asyncio.create_task(process_language(lang)) for lang in target_langs
    ]
    await asyncio.gather(*worker_tasks, return_exceptions=True)


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
