# packages/server/src/trans_hub/presentation/cli/commands/db.py
"""
数据库管理命令，整合了迁移、健康检查、重建和数据审查等功能。
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from trans_hub.management.db_service import DbService
from .._state import CLISharedState

app = typer.Typer(help="数据库管理命令 (迁移、检查、重建等)。", no_args_is_help=True)
console = Console()


def _find_alembic_ini() -> Path:
    """自下而上查找 alembic.ini。"""
    start = Path(__file__).resolve().parent
    # 向上查找 packages/server/alembic.ini
    for p in [*start.parents, start, Path.cwd(), *Path.cwd().parents]:
        cand = p / "packages" / "server" / "alembic.ini"
        if cand.is_file():
            return cand
        cand_root = p / "alembic.ini"
        if cand_root.is_file():
            return cand_root
    raise FileNotFoundError("未找到 Alembic 配置文件 'alembic.ini'。")


@app.command("migrate")
def db_migrate(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="迁移失败时，强制使用 ORM 兜底。"
    ),
) -> None:
    """运行数据库迁移，将 Schema 升级到最新版本。"""
    state: CLISharedState = ctx.obj
    try:
        service = DbService(state.config, str(_find_alembic_ini()))
        service.run_migrations(force=force)
    except Exception as e:
        console.print(f"[bold red]❌ 迁移命令执行失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command("stamp")
def db_stamp(
    ctx: typer.Context,
    revision: str = typer.Argument("head", help="要标记的版本号 (通常是 'head')。"),
) -> None:
    """[高级] 将数据库版本标记为指定值，而不运行迁移脚本。"""
    state: CLISharedState = ctx.obj
    try:
        service = DbService(state.config, str(_find_alembic_ini()))
        service.stamp_version(revision)
    except Exception as e:
        console.print(f"[bold red]❌ 标记命令执行失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command("inspect")
def db_inspect(ctx: typer.Context) -> None:
    """以可读格式显示数据库中的核心内容。"""
    state: CLISharedState = ctx.obj
    try:
        service = DbService(state.config, str(_find_alembic_ini()))
        service.inspect_database()
    except Exception as e:
        console.print(f"[bold red]❌ 审查数据库失败: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command("doctor")
def db_doctor(
    ctx: typer.Context,
    check: bool = typer.Option(False, "--check", help="仅执行健康检查。"),
    deep: bool = typer.Option(False, "--deep", help="在健康检查中运行深度结构探测。"),
    rebuild: bool = typer.Option(False, "--rebuild", help="[危险] 重建数据库。"),
    clear: bool = typer.Option(False, "--clear", help="[危险] 清空数据库数据。"),
    yes: bool = typer.Option(False, "-y", "--yes", help="对危险操作自动应答'是'。"),
) -> None:
    """提供交互式或命令式的数据库诊断与修复工具。"""
    state: CLISharedState = ctx.obj
    try:
        service = DbService(state.config, str(_find_alembic_ini()))

        if any([check, deep, rebuild, clear]):
            if check or deep:
                if not service.check_status(deep=deep):
                    raise typer.Exit(code=1)
            if rebuild:
                if not yes:
                    typer.confirm(f"确定要重建 '{service.app_db_name}' 吗?", abort=True)
                service.rebuild_database()
            if clear:
                if not yes:
                    typer.confirm(f"确定要清空 '{service.app_db_name}' 吗?", abort=True)
                service.clear_database()
        else:
            service.run_interactive_doctor()
    except Exception as e:
        console.print(f"[bold red]❌ 医生工具运行时出错: {e}[/bold red]")
        raise typer.Exit(code=1)
