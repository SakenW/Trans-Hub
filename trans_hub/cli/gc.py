# trans_hub/cli/gc.py
"""处理垃圾回收 (GC) 的 CLI 命令。"""

import asyncio

import questionary
import typer
from rich.console import Console
from rich.table import Table

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator

console = Console()
gc_app = typer.Typer(help="垃圾回收与数据清理")


async def _async_gc_run(
    coordinator: Coordinator, retention_days: int, yes: bool
) -> None:
    """异步执行垃圾回收的核心逻辑。"""
    try:
        await coordinator.initialize()
        console.print(f"正在为超过 {retention_days} 天的非活跃数据生成GC报告...")
        report = await coordinator.run_garbage_collection(retention_days, dry_run=True)

        table = Table(
            title="垃圾回收预演报告", show_header=True, header_style="bold cyan"
        )
        table.add_column("数据类型", style="cyan", width=20)
        table.add_column("将被删除的数量", style="magenta", justify="right")
        table.add_row("业务任务 (Jobs)", str(report.get("deleted_jobs", 0)))
        table.add_row("原文 (Content)", str(report.get("deleted_content", 0)))
        table.add_row("上下文 (Contexts)", str(report.get("deleted_contexts", 0)))
        table.add_row(
            "翻译记录 (Translations)", str(report.get("deleted_translations", 0))
        )
        console.print(table)

        total_to_delete = sum(report.values())
        if total_to_delete == 0:
            console.print("[green]数据库非常干净，无需进行垃圾回收。[/green]")
            return

        if not yes:
            proceed = await questionary.confirm(
                "这是一个破坏性操作，是否继续执行删除？", default=False
            ).ask_async()
            if not proceed:
                console.print("[red]操作已取消。[/red]")
                return

        console.print("[yellow]正在执行删除操作...[/yellow]")
        final_report = await coordinator.run_garbage_collection(
            retention_days, dry_run=False
        )
        deleted_count = sum(final_report.values())
        success_message = (
            f"[bold green]✅ 垃圾回收执行完毕！"
            f"共删除 {deleted_count} 条记录。[/bold green]"
        )
        console.print(success_message)
    finally:
        await coordinator.close()


@gc_app.command("run")
def gc_run(
    ctx: typer.Context,
    retention_days: int = typer.Option(90, "--days", "-d", help="数据保留的最短天数。"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示，直接执行删除。"),
) -> None:
    """
    执行垃圾回收，清理过期的、无关联的旧数据。
    """
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    try:
        # v3.1 最终决定：不再支持旧版 Python，直接使用 asyncio.run
        asyncio.run(_async_gc_run(coordinator, retention_days, yes))
    except Exception as e:
        if "Not a tty" in str(e) or isinstance(e, RuntimeError):
            error_msg = (
                "[bold red]❌ 错误：此命令需要交互式终端。"
                "请使用 --yes 标志在非交互式环境中运行。[/bold red]"
            )
            console.print(error_msg)
        else:
            console.print(f"[bold red]❌ 执行失败: {e}[/bold red]")
        raise typer.Exit(code=1)
