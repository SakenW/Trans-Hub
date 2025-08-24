# packages/server/src/trans_hub/presentation/cli/main.py

import os
from typing import Literal

import typer
from rich.console import Console
from rich.traceback import install as install_rich_tracebacks

from trans_hub.bootstrap import create_app_config
from trans_hub.observability.logging_config import setup_logging

from ._state import CLISharedState
from .commands import db, request, status

install_rich_tracebacks(show_locals=True, word_wrap=True)

app = typer.Typer(
    name="trans-hub",
    help="🤖 Trans-Hub Server 命令行管理工具。",
    add_completion=False,
    no_args_is_help=True,
)

app.add_typer(db.app, name="db")
app.add_typer(request.app, name="request")
app.add_typer(status.app, name="status")

console = Console()


@app.callback()
def main(ctx: typer.Context):
    """
    主回调函数，在任何子命令执行前运行，负责加载配置和初始化日志。
    """
    try:
        env_mode_str = os.getenv("TRANSHUB_ENV", "dev").lower()
        if env_mode_str not in ("prod", "dev", "test"):
            env_mode_str = "dev"

        env_mode: Literal["prod", "dev", "test"] = env_mode_str  # type: ignore

        config = create_app_config(env_mode=env_mode)

        # CLI 使用的日志配置
        setup_logging(
            log_level=config.logging.level,
            log_format=config.logging.format,  # 尊重 .env 中的配置
            service="trans-hub-cli",
        )

        ctx.obj = CLISharedState(config=config)
    except Exception as e:
        console.print(f"[bold red]❌ 启动失败：无法加载配置: {e}[/bold red]")
        raise typer.Exit(code=1) from e
