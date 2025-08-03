# trans_hub/cli/gc/main.py
"""
Trans-Hub Garbage Collection CLI 子模块。
"""

import asyncio

import questionary
import structlog
from rich.console import Console
from rich.table import Table

from trans_hub.coordinator import Coordinator

log = structlog.get_logger("trans_hub.cli.gc")
console = Console()


def gc(
    coordinator: Coordinator,
    loop: asyncio.AbstractEventLoop,
    retention_days: int = 90,
    dry_run: bool = False,
) -> None:
    """
    执行数据库垃圾回收，清理过期的、无关联的旧数据。
    """
    try:
        mode = "Dry Run" if dry_run else "执行"
        console.print(
            f"[yellow]即将为超过 {retention_days} 天的非活跃任务执行垃圾回收 "
            f"({mode})...[/yellow]"
        )

        report = loop.run_until_complete(
            coordinator.run_garbage_collection(retention_days, True)
        )

        table = Table(title="垃圾回收预报告")
        table.add_column("项目", style="cyan")
        table.add_column("将被删除数量", style="magenta", justify="right")
        table.add_row("关联任务 (Jobs)", str(report.get("deleted_jobs", 0)))
        table.add_row("原文内容 (Content)", str(report.get("deleted_content", 0)))
        table.add_row("上下文 (Contexts)", str(report.get("deleted_contexts", 0)))

        console.print(table)

        if all(v == 0 for v in report.values()):
            console.print("[green]数据库很干净，无需进行垃圾回收。[/green]")
            return

        if not dry_run:
            # 使用 run_until_complete 来运行异步的 questionary.confirm
            proceed = loop.run_until_complete(
                questionary.confirm(
                    "这是一个破坏性操作，是否继续执行删除？",
                    default=False,
                    auto_enter=False,
                ).ask_async()
            )

            if not proceed:
                console.print("[red]操作已取消。[/red]")
                return

            console.print("[yellow]正在执行删除操作...[/yellow]")
            loop.run_until_complete(
                coordinator.run_garbage_collection(retention_days, False)
            )
            console.print("[green]✅ 垃圾回收执行完毕！[/green]")
            # 注意：这里可能需要调整，因为 assert 在生产环境中通常不会执行
            # assert final_report == report, "最终报告与预报告不符，可能存在并发问题"
    except Exception as e:  # pragma: no cover
        log.exception("垃圾回收执行失败")
        console.print(f"[red]垃圾回收失败: {e}[/red]")
        raise SystemExit(1)
