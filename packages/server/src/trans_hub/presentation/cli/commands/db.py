# packages/server/src/trans_hub/presentation/cli/commands/db.py
"""
处理数据库迁移相关的 CLI 命令。
"""
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="数据库管理命令 (迁移等)。")
console = Console()

@app.command("migrate")
def db_migrate() -> None:
    """
    运行数据库迁移。

    使用 Alembic 将数据库 Schema 升级到代码中定义的最新版本。
    """
    console.print("[cyan]正在启动数据库迁移流程...[/cyan]")
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig
        from trans_hub.config import TransHubConfig

        config = TransHubConfig()
        
        # Alembic 需要相对于项目根目录的路径
        # 假设此文件在 packages/server/src/trans_hub/presentation/cli/commands/
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent.parent
        alembic_cfg_path = project_root / "packages/server/alembic.ini" # 假设 alembic.ini 在 server 包下
        
        if not alembic_cfg_path.is_file():
            # Fallback for different execution contexts
            alembic_cfg_path = Path.cwd() / "packages/server/alembic.ini"
            if not alembic_cfg_path.is_file():
                 raise FileNotFoundError(f"Alembic 配置文件 'alembic.ini' 未在预设路径找到。")

        console.print(f"使用 Alembic 配置文件: [dim]{alembic_cfg_path}[/dim]")
        
        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        
        # 确保 Alembic 使用与应用相同的数据库 URL
        # Alembic 需要同步驱动
        sync_db_url = config.database_url.replace("+aiosqlite", "").replace("+asyncpg", "")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
        
        console.print(f"目标数据库: [yellow]{sync_db_url}[/yellow]")
        command.upgrade(alembic_cfg, "head")
        
        console.print("[bold green]✅ 数据库迁移成功完成！[/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ 数据库迁移失败: {e}[/bold red]")
        console.print_exception(show_locals=True)
        raise typer.Exit(code=1)