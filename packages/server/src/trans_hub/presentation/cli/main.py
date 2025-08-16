# packages/server/src/trans_hub/presentation/cli/main.py
"""
Trans-Hub Server CLI 的主入口点。
"""

import typer
from rich.console import Console
from rich.traceback import install as install_rich_tracebacks

from trans_hub.bootstrap import create_app_config  # [修改] 导入新的工厂函数
from trans_hub.observability.logging_config import setup_logging

from ._state import CLISharedState
from .commands import db, request, status

# 安装 Rich 全局回溯处理器，美化所有未捕获的异常
install_rich_tracebacks(show_locals=True, word_wrap=True)

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


@app.callback()
def main(ctx: typer.Context):
    """
    主回调函数，在任何子命令执行前运行，负责加载配置和初始化日志。
    """
    try:
        # [修改] 使用新的引导程序加载生产配置
        config = create_app_config(env_mode="prod")
        setup_logging(log_level=config.logging.level, log_format=config.logging.format)
        ctx.obj = CLISharedState(config=config)
    except Exception as e:
        console.print(f"[bold red]❌ 启动失败：无法加载配置: {e}[/bold red]")
        raise typer.Exit(code=1) from e
