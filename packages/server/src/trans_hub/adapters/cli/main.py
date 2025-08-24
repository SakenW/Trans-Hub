# packages/server/src/trans_hub/adapters/cli/main.py

import sys
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.traceback import install as install_rich_tracebacks
from trans_hub.bootstrap.init import bootstrap_app
from trans_hub.observability.logging_config import setup_logging_from_config

from .commands import db, request, status, worker

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
app.add_typer(worker.app, name="worker")

console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    env: Annotated[
        str, typer.Option("--env", help="运行环境 (dev, test, prod)")
    ] = "dev",
):
    """
    主回调函数，在任何子命令执行前运行，负责加载配置和初始化日志。
    """
    if ctx.resilient_parsing:
        return

    env_mode: Literal["prod", "dev", "test"] = env.lower()  # type: ignore

    # 引导程序现在是同步的
    container = bootstrap_app(env_mode=env_mode)

    # [关键] Wire 容器到需要注入的模块
    container.wire(
        modules=[
            sys.modules[__name__],
            "trans_hub.adapters.cli.commands.db",
            "trans_hub.adapters.cli.commands.request",
            "trans_hub.adapters.cli.commands.status",
            "trans_hub.adapters.cli.commands.worker",
        ]
    )

    # 初始化日志
    config = container.config()
    setup_logging_from_config(config, service="trans-hub-cli")

    # 将容器实例存入上下文
    ctx.obj = container
