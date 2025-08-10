# trans_hub/cli/main.py
# [v3.1 - 添加 status 子命令]
"""Trans-Hub CLI 的主入口点。"""

from typing import Annotated

import typer
from rich.console import Console

import trans_hub
from trans_hub.cli.db import db_app
from trans_hub.cli.gc import gc_app
from trans_hub.cli.request import request_app
from trans_hub.cli.state import State

# [新增] 导入新的 status 应用
from trans_hub.cli.status import status_app
from trans_hub.cli.worker import worker_app
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging

# 创建主 Typer 应用
app = typer.Typer(
    name="trans-hub",
    help="🤖 Trans-Hub: 一个基于 UIDA 的企业级本地化后端引擎。",
    add_completion=False,
    no_args_is_help=True,
)

# 注册子命令/子应用
app.add_typer(db_app, name="db")
app.add_typer(request_app, name="request")
# [新增] 注册 status 应用
app.add_typer(status_app, name="status")
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
    """主回调函数，在任何子命令执行前运行。"""
    try:
        config = TransHubConfig()
        setup_logging(log_level=config.logging.level, log_format=config.logging.format)
        discover_engines()
        ctx.obj = State(config=config)
    except Exception as e:
        console.print("[bold red]❌ 启动失败：无法加载配置或初始化日志。[/bold red]")
        console.print(f"[dim]{e}[/dim]")
        raise typer.Exit(code=1) from e
