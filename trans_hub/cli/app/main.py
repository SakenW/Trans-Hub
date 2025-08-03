# trans_hub/cli/app/main.py
"""
Trans-Hub Application CLI 子模块。
"""

import asyncio
import signal
import sys
from typing import NoReturn

import structlog
import typer
from rich.console import Console

from trans_hub.coordinator import Coordinator

log = structlog.get_logger("trans_hub.cli.app")
console = Console()
app = typer.Typer(help="Trans-Hub 应用主入口")


def _signal_handler(coordinator: Coordinator, loop: asyncio.AbstractEventLoop) -> None:
    """
    信号处理器，用于优雅地关闭应用。
    """
    console.print("[yellow]正在关闭应用...[/yellow]")
    if coordinator:
        log.info("正在关闭协调器...")
        loop.run_until_complete(coordinator.close())
        log.info("协调器已关闭")
    loop.stop()
    console.print("[green]应用已关闭。[/green]")
    sys.exit(0)


def run_app(coordinator: Coordinator, loop: asyncio.AbstractEventLoop) -> NoReturn:
    """
    运行Trans-Hub应用主循环。
    """
    try:
        # 设置信号处理器以实现优雅关闭
        signal.signal(signal.SIGINT, lambda s, f: _signal_handler(coordinator, loop))
        signal.signal(signal.SIGTERM, lambda s, f: _signal_handler(coordinator, loop))

        # 运行事件循环
        loop.run_forever()
    except KeyboardInterrupt:
        console.print("[yellow]收到中断信号，正在关闭...[/yellow]")
        _signal_handler(coordinator, loop)
    except Exception as e:
        log.error("应用运行时发生未预期错误", error=str(e), exc_info=True)
        console.print(f"[red]❌ 应用运行时发生未预期错误: {e}[/red]")
        sys.exit(1)
    finally:
        # 确保协调器已关闭
        if coordinator:
            log.info("应用退出，正在关闭协调器...")
            loop.run_until_complete(coordinator.close())
            log.info("协调器已关闭")
        loop.close()
        # 重置全局状态，允许后续命令重新初始化
        try:
            import trans_hub.cli as cli_main

            cli_main._coordinator = None
            cli_main._loop = None
        except Exception:
            pass
        # 确保函数永远不会返回
        raise RuntimeError("This function should never return")
