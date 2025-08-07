# trans_hub/cli/db.py
"""处理数据库相关操作的 CLI 命令。"""

from pathlib import Path

import structlog
import typer
from rich.console import Console

from alembic import command

# [核心修改] 导入 Alembic 的配置和命令 API
from alembic.config import Config
from trans_hub.cli.state import State

logger = structlog.get_logger(__name__)
console = Console()
db_app = typer.Typer(help="数据库管理命令")


@db_app.command("migrate")
def db_migrate(ctx: typer.Context) -> None:
    """使用 Alembic 对数据库执行所有待处理的迁移，使其达到最新版本。"""
    state: State = ctx.obj
    db_path = state.config.database_url

    if "sqlite" in db_path and ":memory:" in db_path:
        console.print("[yellow]警告：无法对内存数据库执行永久性迁移。[/yellow]")
        raise typer.Exit()

    console.print(f"数据库目标: [cyan]{db_path}[/cyan]")
    console.print("正在使用 Alembic 应用数据库迁移...")

    try:
        # 寻找 alembic.ini 文件的路径
        alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
        if not alembic_cfg_path.exists():
            raise FileNotFoundError("alembic.ini 配置文件未找到！")

        # 创建 Alembic 配置对象
        alembic_cfg = Config(str(alembic_cfg_path))

        # [核心修改] 调用 Alembic 的升级命令
        command.upgrade(alembic_cfg, "head")

        console.print("[bold green]✅ 数据库迁移成功完成！[/bold green]")
    except Exception as e:
        logger.error("数据库迁移过程中发生错误。", exc_info=True)
        console.print(
            f"[bold red]❌ 数据库迁移失败: {e}[/bold red]\n"
            "[dim]请检查 alembic.ini 配置和数据库连接。[/dim]"
        )
        raise typer.Exit(code=1) from e
