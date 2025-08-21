# packages/server/src/trans_hub/presentation/cli/main.py
import os
import sys
from typing import Literal

import typer
from rich.console import Console
from rich.traceback import install as install_rich_tracebacks

# [DI 重构] 从新的 bootstrap 导入核心函数
from trans_hub.bootstrap import create_app_config, create_container

# [DI 重构] 导入所有需要 wiring 的命令模块
from .commands import db, request, status, worker

install_rich_tracebacks(show_locals=True, word_wrap=True)

app = typer.Typer(
    name="trans-hub",
    help="🤖 Trans-Hub Server 命令行管理工具。",
    add_completion=False,
    no_args_is_help=True,
)

# 注册所有子命令
app.add_typer(db.app, name="db")
app.add_typer(request.app, name="request")
app.add_typer(status.app, name="status")
app.add_typer(worker.app, name="worker")

console = Console()


@app.callback()
def main(ctx: typer.Context):
    """
    [DI 重构] 主回调函数，负责创建和装配 DI 容器，并管理其生命周期。
    """
    try:
        env_mode_str = os.getenv("TRANSHUB_ENV", "dev").lower()
        if env_mode_str not in ("prod", "dev", "test"):
            env_mode_str = "dev"
        env_mode: Literal["prod", "dev", "test"] = env_mode_str  # type: ignore

        config = create_app_config(env_mode=env_mode)

        # 创建容器
        container = create_container(config, service_name="trans-hub-cli")

        # 将容器附加到上下文，供所有子命令使用
        ctx.obj = container

        # [关键] 对所有需要注入的模块执行 wiring
        container.wire(
            modules=[
                sys.modules[__name__],
                db,
                request,
                status,
                worker,
                # 确保 db_service 也能被注入
                "trans_hub.management.db_service",
            ]
        )

        # 定义资源关闭的回调
        def shutdown_resources():
            console.print("[dim]CLI 命令执行完毕，正在关闭资源...[/dim]")
            container.shutdown_resources()
            console.print("[green]✅ 资源已安全关闭。[/green]")

        # 注册回调，确保在命令执行完毕后（无论成功或失败）都能关闭资源
        ctx.call_on_close(shutdown_resources)

        # 初始化资源
        container.init_resources()

    except Exception as e:
        console.print(
            f"[bold red]❌ 启动失败：无法加载配置或初始化容器: {e}[/bold red]"
        )
        console.print_exception(show_locals=True)
        raise typer.Exit(code=1) from e
