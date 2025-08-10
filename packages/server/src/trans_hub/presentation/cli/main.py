# packages/server/src/trans_hub/presentation/cli/main.py
"""
Trans-Hub Server CLI 的主入口点。
"""
from typing import Annotated

import typer
from rich.console import Console

from trans_hub.config import TransHubConfig
from trans_hub.observability.logging_config import setup_logging

from .commands import db, request, status

app = typer.Typer(
    name="trans-hub",
    help="🤖 Trans-Hub Server 命令行管理工具。",
    add_completion=False,
    no_args_is_help=True,
)

# 注册子命令
app.add_typer(db.app, name="db")
app.add_typer(request.app, name="request")
app.add_typer(status.app, name="status")

console = Console()

class CLISharedState:
    """用于在 Typer 上下文中传递共享对象的容器。"""
    def __init__(self, config: TransHubConfig):
        self.config = config

@app.callback()
def main(ctx: typer.Context):
    """
    主回调函数，在任何子命令执行前运行，负责加载配置和初始化日志。
    """
    try:
        config = TransHubConfig()
        setup_logging(log_level=config.logging.level, log_format=config.logging.format)
        ctx.obj = CLISharedState(config=config)
    except Exception as e:
        console.print(f"[bold red]❌ 启动失败：无法加载配置: {e}[/bold red]")
        raise typer.Exit(code=1) from e