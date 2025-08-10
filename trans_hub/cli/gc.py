# trans_hub/cli/gc.py
"""处理垃圾回收 (GC) 的 CLI 命令 (UIDA 架构版)。"""

import asyncio
from typing import Annotated

import questionary
import typer
from rich.console import Console
from rich.table import Table

from trans_hub.cli.state import State
from trans_hub.cli.utils import create_coordinator
from trans_hub.coordinator import Coordinator

console = Console()
gc_app = typer.Typer(help="垃圾回收与数据清理 (UIDA 模式)")


async def _async_gc_run(
    coordinator: Coordinator,
    content_days: int,
    tm_days: int,
    yes: bool,
) -> None:
    """异步执行垃圾回收的核心逻辑。"""
    try:
        await coordinator.initialize()
        console.print("正在生成垃圾回收预演报告...")
        report = await coordinator.run_garbage_collection(
            archived_content_retention_days=content_days,
            unused_tm_retention_days=tm_days,
            dry_run=True,
        )

        table = Table(
            title="垃圾回收预演报告", show_header=True, header_style="bold cyan"
        )
        table.add_column("数据类型", style="cyan", width=35)
        table.add_column("将被删除的数量", style="magenta", justify="right")
        table.add_row(
            f"已归档超过 {content_days} 天的内容",
            str(report.get("deleted_archived_content", 0)),
        )
        table.add_row(
            f"超过 {tm_days} 天未使用的翻译记忆",
            str(report.get("deleted_unused_tm_entries", 0)),
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
            archived_content_retention_days=content_days,
            unused_tm_retention_days=tm_days,
            dry_run=False,
        )
        deleted_count = sum(final_report.values())
        console.print(
            f"[bold green]✅ 垃圾回收执行完毕！共删除 {deleted_count} 条记录。[/bold green]"
        )
    finally:
        await coordinator.close()


@gc_app.command("run")
def gc_run(
    ctx: typer.Context,
    content_days: Annotated[
        int, typer.Option("--content-days", help="删除已归档超过此天数的内容。")
    ] = 90,
    tm_days: Annotated[
        int, typer.Option("--tm-days", help="删除超过此天数未使用的翻译记忆。")
    ] = 365,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="跳过确认提示，直接执行删除。")
    ] = False,
) -> None:
    """执行垃圾回收，清理已归档的内容和长期未使用的翻译记忆。"""
    state: State = ctx.obj
    coordinator = create_coordinator(state.config)
    try:
        asyncio.run(_async_gc_run(coordinator, content_days, tm_days, yes))
    except (RuntimeError, Exception) as e:
        if "Not a tty" in str(e):
            console.print(
                "[bold red]❌ 错误：此命令需要交互式终端。请使用 --yes 标志运行。[/bold red]"
            )
        else:
            console.print(f"[bold red]❌ 执行失败: {e}[/bold red]")
        raise typer.Exit(code=1) from e
