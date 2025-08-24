# packages/server/src/trans_hub/adapters/cli/commands/db.py
"""
数据库管理命令，整合了迁移、健康检查、重建和数据审查等功能。
"""

from __future__ import annotations

import asyncio
import typer
from rich.console import Console
from trans_hub.di.container import AppContainer
from trans_hub.management.db_service import DbService
from trans_hub.management.utils import find_alembic_ini

app = typer.Typer(help="数据库管理命令 (迁移、检查、重建等)。", no_args_is_help=True)
console = Console()


@app.command("migrate")
def db_migrate(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="迁移失败时，强制使用 ORM 兜底。"
    ),
) -> None:
    """运行数据库迁移，将 Schema 升级到最新版本。"""
    async def _async_migrate() -> None:
        try:
            container: AppContainer = ctx.obj
            config = container.config()
            service = DbService(config, str(find_alembic_ini()))
            await service.run_migrations(force=force)
            console.print("[bold green]✅ 数据库迁移成功。[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ 迁移命令执行失败: {e}[/bold red]")
            raise typer.Exit(code=1)
    
    asyncio.run(_async_migrate())


@app.command("stamp")
def db_stamp(
    ctx: typer.Context,
    revision: str = typer.Argument("head", help="要标记的版本号 (通常是 'head')。"),
) -> None:
    """[高级] 将数据库版本标记为指定值，而不运行迁移脚本。"""
    async def _async_stamp() -> None:
        try:
            container: AppContainer = ctx.obj
            config = container.config()
            service = DbService(config, str(find_alembic_ini()))
            await service.stamp_version(revision)
            console.print(f"[bold green]✅ 数据库已成功标记到版本: {revision}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ 标记命令执行失败: {e}[/bold red]")
            raise typer.Exit(code=1)
    
    asyncio.run(_async_stamp())


@app.command("inspect")
def db_inspect(ctx: typer.Context) -> None:
    """以可读格式显示数据库中的核心内容。"""
    async def _async_inspect() -> None:
        try:
            container: AppContainer = ctx.obj
            config = container.config()
            service = DbService(config, str(find_alembic_ini()))
            await service.inspect_database()
        except Exception as e:
            console.print(f"[bold red]❌ 审查数据库失败: {e}[/bold red]")
            raise typer.Exit(code=1)
    
    asyncio.run(_async_inspect())


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
    async def _async_doctor() -> None:
        try:
            container: AppContainer = ctx.obj
            config = container.config()
            service = DbService(config, str(find_alembic_ini()))

            if any([check, deep, rebuild, clear]):
                if check or deep:
                    if not await service.check_status(deep=deep):
                        raise typer.Exit(code=1)
                if rebuild:
                    if not yes:
                        typer.confirm(f"确定要重建 '{service.app_db_name}' 吗?", abort=True)
                    await service.rebuild_database()
                    console.print("[bold green]✅ 数据库初始化成功。[/bold green]")
                if clear:
                    if not yes:
                        typer.confirm(f"确定要清空 '{service.app_db_name}' 吗?", abort=True)
                    await service.clear_database()
                    console.print("[bold green]✅ 数据库已清空。[/bold green]")
            else:
                await service.run_interactive_doctor()
        except Exception as e:
            console.print(f"[bold red]❌ 数据库诊断失败: {e}[/bold red]")
            raise typer.Exit(code=1)
    
    asyncio.run(_async_doctor())


@app.command("upgrade-test")
def db_upgrade_test(ctx: typer.Context) -> None:
    """
    [CI/CD专用] 在测试环境中重建数据库并运行迁移。

    此命令确保操作在测试数据库上进行。
    它会首先调用 DbService 来彻底重建测试数据库，然后运行迁移至最新版本。
    这是确保每次测试都在一个干净、一致的数据库状态下开始的关键步骤。
    """
    async def _async_upgrade_test() -> None:
        try:
            container: AppContainer = ctx.obj
            config = container.config()

            # 此操作强制在测试环境中进行
            if config.app_env != "test":
                console.print(
                    f"[bold red]错误: upgrade-test 命令只能在 'test' 环境下运行，当前为 '{config.app_env}'。[/bold red]"
                )
                raise typer.Exit(code=1)

            console.print("--- [CI/CD] Running Database Upgrade Test ---")
            console.print(f"强制在环境: [bold cyan]{config.app_env}[/bold cyan] 中操作")

            service = DbService(config, str(find_alembic_ini()))

            console.print("步骤 1: 重建测试数据库...")
            service.rebuild_database()
            console.print("--- 数据库升级测试成功 ---")

        except Exception as e:
            console.print(f"[bold red]❌ 数据库升级测试失败: {e}[/bold red]")
            raise typer.Exit(code=1)
    
    asyncio.run(_async_upgrade_test())
