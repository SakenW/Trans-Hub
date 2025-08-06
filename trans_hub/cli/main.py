# trans_hub/cli/main.py
"""Trans-Hub CLI 的主入口点。"""

from typing import Annotated

import typer
from rich.console import Console

import trans_hub
from trans_hub.cli.db import db_app
from trans_hub.cli.gc import gc_app
from trans_hub.cli.request import request_app
from trans_hub.cli.state import State
from trans_hub.cli.worker import worker_app
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging

# 创建主 Typer 应用
app = typer.Typer(
    name="trans-hub",
    help="🤖 Trans-Hub: 一个可嵌入的、带持久化存储的智能本地化后端引擎。",
    add_completion=False,
    no_args_is_help=True,
)

# 注册子命令/子应用
app.add_typer(db_app, name="db")
app.add_typer(request_app, name="request")
app.add_typer(gc_app, name="gc")
app.add_typer(worker_app, name="worker")

console = Console()


def version_callback(value: bool) -> None:
    """处理 --version 选项的回调函数。"""
    if value:
        console.print(f"Trans-Hub [bold cyan]v{trans_hub.__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="显示版本信息并退出。",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """
    主回调函数，在任何子命令执行前运行。

    v3.1 最终修复：确保日志配置先于引擎发现。
    """
    try:
        config = TransHubConfig()
        # 1. 首先配置日志系统
        setup_logging(log_level=config.logging.level, log_format=config.logging.format)
        # 2. 然后执行引擎发现
        discover_engines()
        # 3. 最后将配置存入上下文
        ctx.obj = State(config=config)
    except Exception as e:
        console.print("[bold red]❌ 启动失败：无法加载配置或初始化日志。[/bold red]")
        console.print(f"[dim]{e}[/dim]")
        raise typer.Exit(code=1) from e
