# trans_hub/cli/db.py
"""处理数据库相关操作的 CLI 命令。"""

from pathlib import Path

import structlog
import typer
from rich.console import Console

from trans_hub.cli.state import State
from trans_hub.db.schema_manager import apply_migrations

logger = structlog.get_logger(__name__)
console = Console()
db_app = typer.Typer(help="数据库管理命令")


@db_app.command("migrate")
def db_migrate(ctx: typer.Context) -> None:
    """
    对数据库执行所有待处理的迁移。

    此命令会从配置中读取数据库路径，并应用所有必要的 schema 变更。
    """
    state: State = ctx.obj
    db_path = state.config.db_path

    if db_path == ":memory:":
        console.print("[yellow]警告：无法对内存数据库执行永久性迁移。[/yellow]")
        raise typer.Exit()

    console.print(f"数据库路径: [cyan]{Path(db_path).resolve()}[/cyan]")
    console.print("正在应用数据库迁移...")

    try:
        # 确保数据库文件的父目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(db_path)
        console.print("[bold green]✅ 数据库迁移成功完成！[/bold green]")
    except Exception as e:
        logger.error("数据库迁移过程中发生错误。", exc_info=True)
        console.print(
            "[bold red]❌ 数据库迁移失败！请检查日志获取详细信息。[/bold red]"
        )
        raise typer.Exit(code=1) from e
