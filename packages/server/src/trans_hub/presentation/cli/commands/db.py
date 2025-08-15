# packages/server/src/trans_hub/presentation/cli/commands/db.py
"""
数据库管理命令，整合了迁移、健康检查、重建和数据审查等功能。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from alembic import command
from alembic.config import Config as AlembicConfig

from trans_hub.config_loader import load_config_from_env

app = typer.Typer(
    help="数据库管理命令 (迁移、检查、重建等)。",
    no_args_is_help=True
)
console = Console()

# --- 内部辅助函数 ---

def _find_alembic_ini(start: Optional[Path] = None) -> Path:
    """自下而上查找 alembic.ini。"""
    start = (start or Path(__file__).resolve()).parent
    # 向上查找 packages/server/alembic.ini
    for p in [*start.parents, start, Path.cwd(), *Path.cwd().parents]:
        cand = p / "packages" / "server" / "alembic.ini"
        if cand.is_file():
            return cand
        cand_root = p / "alembic.ini"
        if cand_root.is_file():
            return cand_root
    raise FileNotFoundError("未找到 Alembic 配置文件 'alembic.ini'。")

def _to_sync_driver(async_dsn: str) -> str:
    """将运行期异步 DSN 转为同步 DSN（仅切 driver，保留主机/库名等）。"""
    url = make_url(async_dsn)
    backend = url.get_backend_name()
    if backend == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    elif backend == "sqlite":
        url = url.set(drivername="sqlite")
    elif backend == "mysql":
        url = url.set(drivername="mysql+pymysql")
    else:
        raise typer.BadParameter(f"不支持的数据库后端：{backend!r}")
    return str(url)

# --- CLI 命令 ---

@app.command("migrate")
def db_migrate() -> None:
    """运行数据库迁移，将 Schema 升级到最新版本。"""
    console.print("[cyan]正在启动数据库迁移流程...[/cyan]")
    try:
        cfg = load_config_from_env(mode="prod", strict=True)
        sync_db_url_str = _to_sync_driver(cfg.database.url)
        url_obj = make_url(sync_db_url_str)
        
        alembic_cfg_path = _find_alembic_ini()
        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        
        # 强制使用代码中生成的、未脱敏的 URL
        real_url_for_alembic = url_obj.render_as_string(hide_password=False)
        # 对 '%' 符号进行转义以兼容 configparser
        safe_url_for_configparser = real_url_for_alembic.replace('%', '%%')
        alembic_cfg.set_main_option("sqlalchemy.url", safe_url_for_configparser)

        console.print(f"使用 Alembic 配置文件: [dim]{alembic_cfg_path}[/dim]")
        # 打印时使用 hide_password=True 进行脱敏
        safe_url_for_print = url_obj.render_as_string(hide_password=True)
        console.print(f"迁移目标数据库: [yellow]{safe_url_for_print}[/yellow]")
        
        command.upgrade(alembic_cfg, "head")
        console.print("[bold green]✅ 数据库迁移成功完成！[/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ 数据库迁移失败: {e}[/bold red]")
        console.print_exception(show_locals=False)
        raise typer.Exit(code=1)

@app.command("check")
def db_check() -> None:
    """执行数据库健康检查，验证连接、权限和迁移状态。"""
    console.print("[cyan]正在执行数据库健康检查...[/cyan]")
    errors = 0
    try:
        cfg = load_config_from_env(mode="prod", strict=True)
        maint_url = cfg.maintenance_database_url
        if not maint_url:
            raise ValueError("未配置维护数据库 URL (TRANSHUB_MAINTENANCE_DATABASE_URL)")
        
        engine = create_engine(maint_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            console.print(f"✅ 维护库连接成功: [yellow]{make_url(maint_url).render_as_string(hide_password=True)}[/yellow]")
    except Exception as e:
        console.print(f"❌ 维护库连接失败: {e}")
        errors += 1

    console.print(f"\n[bold]{'✅ 健康检查通过' if errors == 0 else '❌ 健康检查发现问题'}[/bold]")
    if errors > 0:
        raise typer.Exit(code=1)

@app.command("rebuild")
def db_rebuild(
    yes: bool = typer.Option(False, "--yes", "-y", help="自动确认，跳过危险操作提示。")
) -> None:
    """[危险] 删除并重建数据库，然后运行迁移。仅限开发环境使用！"""
    console.print(Panel("[bold red]警告：此操作将永久删除数据库中的所有数据！[/bold red]", border_style="red"))
    if not yes:
        typer.confirm("您确定要继续吗？", abort=True)
    
    try:
        cfg = load_config_from_env(mode="prod", strict=True)
        maint_url_str = cfg.maintenance_database_url
        app_url_str = cfg.database.url
        if not maint_url_str:
            raise ValueError("未配置维护数据库 URL (TRANSHUB_MAINTENANCE_DATABASE_URL)")
        
        app_db_name = make_url(app_url_str).database
        maint_engine = create_engine(maint_url_str, isolation_level="AUTOCOMMIT")

        with maint_engine.connect() as conn:
            console.print(f"正在删除数据库: [yellow]{app_db_name}[/yellow]")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{app_db_name}" WITH (FORCE)'))
            console.print(f"正在创建数据库: [yellow]{app_db_name}[/yellow]")
            conn.execute(text(f'CREATE DATABASE "{app_db_name}"'))
        
        console.print("数据库重建完成，现在开始迁移...")
        db_migrate()
        console.print(f"[bold green]✅ 数据库 '{app_db_name}' 已成功重建并迁移！[/bold green]")
    except Exception as e:
        console.print(f"[bold red]❌ 重建数据库失败: {e}[/bold red]")
        raise typer.Exit(code=1)

@app.command("inspect")
def db_inspect() -> None:
    """以可读格式显示数据库中的核心内容。"""
    try:
        # 使用延迟导入，避免不必要的依赖
        from ._db_inspect_impl import inspect_database_impl 
        
        cfg = load_config_from_env(mode="prod", strict=True)
        sync_db_url = _to_sync_driver(cfg.database.url)
        inspect_database_impl(sync_db_url)
    except ImportError:
        console.print("[bold red]错误: `_db_inspect_impl` 模块不存在或无法导入。[/bold red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]❌ 审查数据库失败: {e}[/bold red]")
        raise typer.Exit(code=1)