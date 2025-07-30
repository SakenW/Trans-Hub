# tools/inspect_db.py
"""一个专业的命令行工具，用于检查和解读 Trans-Hub (v3.2+) 数据库的内容。"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    from trans_hub.logging_config import setup_logging
except (ImportError, IndexError):
    print("错误: 无法将项目根目录添加到 sys.path。请确保此脚本位于 'tools' 目录下。")
    sys.exit(1)

import aiosqlite
import structlog
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

log = structlog.get_logger(__name__)


class DatabaseInspector:
    """封装了检查 Trans-Hub 数据库所有逻辑的类。"""

    def __init__(self, db_path: str, console: Console):
        """
        初始化数据库检查器。

        Args:
            db_path (str): 目标 SQLite 数据库文件的路径。
            console (Console): 用于富文本输出的 Rich Console 实例。

        """
        self.db_path = db_path
        self.console = console
        self.conn: Optional[aiosqlite.Connection] = None

    async def inspect(self) -> None:
        """执行数据库检查的主流程。"""
        if not os.path.exists(self.db_path):
            log.error("数据库文件不存在。", path=self.db_path)
            return

        try:
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            log.info("✅ 成功连接到数据库", path=self.db_path)
            await self._print_summary_stats()
            await self._print_detailed_records()
        finally:
            if self.conn:
                await self.conn.close()
                log.info("数据库连接已关闭。")

    async def _print_summary_stats(self) -> None:
        """查询并打印数据库的统计概览信息。"""
        assert self.conn is not None
        self.console.print(
            Panel("[bold cyan]Trans-Hub 数据库统计概览[/bold cyan]", expand=False)
        )
        queries = {
            "总内容条目 (th_content)": "SELECT COUNT(*) FROM th_content;",
            "总上下文条目 (th_contexts)": "SELECT COUNT(*) FROM th_contexts;",
            "总关联任务 (th_jobs)": "SELECT COUNT(*) FROM th_jobs;",
            "总翻译记录 (th_translations)": "SELECT COUNT(*) FROM th_translations;",
            "待处理 (PENDING)": "SELECT COUNT(*) FROM th_translations WHERE status = 'PENDING';",
            "翻译中 (TRANSLATING)": "SELECT COUNT(*) FROM th_translations WHERE status = 'TRANSLATING';",
            "已失败 (FAILED)": "SELECT COUNT(*) FROM th_translations WHERE status = 'FAILED';",
            "死信队列条目 (DLQ)": "SELECT COUNT(*) FROM th_dead_letter_queue;",
        }
        table = Table(show_header=False, box=None)
        table.add_column("项目", style="dim")
        table.add_column("数量", justify="right")
        async with self.conn.cursor() as cursor:
            for title, query in queries.items():
                try:
                    await cursor.execute(query)
                    result = await cursor.fetchone()
                    count = result[0] if result else 0
                    table.add_row(f"{title}:", f"[bold green]{count}[/bold green]")
                except aiosqlite.OperationalError:
                    table.add_row(f"{title}:", "[yellow]表不存在[/yellow]")
        self.console.print(table)
        self.console.print("")

    async def _print_detailed_records(self) -> None:
        """查询并以富文本格式详细打印每一条翻译记录。"""
        assert self.conn is not None
        self.console.print(Panel("[bold cyan]详细翻译记录[/bold cyan]", expand=False))
        query = """
        SELECT
            tr.id AS translation_id, tr.lang_code, tr.status, tr.translation_content,
            tr.engine, tr.engine_version, tr.last_updated_at, c.value AS original_content,
            ctx.value AS context_json, j.business_id, j.last_requested_at
        FROM th_translations tr
        JOIN th_content c ON tr.content_id = c.id
        LEFT JOIN th_contexts ctx ON tr.context_id = ctx.id
        LEFT JOIN th_jobs j ON tr.content_id = j.content_id
            AND COALESCE(tr.context_id, '') = COALESCE(j.context_id, '')
        ORDER BY tr.last_updated_at DESC;
        """
        async with self.conn.cursor() as cursor:
            await cursor.execute(query)
            rows: list[aiosqlite.Row] = list(await cursor.fetchall())
        if not rows:
            self.console.print("[yellow]数据库中没有找到翻译记录。[/yellow]")
            return
        for i, row in enumerate(rows):
            record_panel = self._build_single_record_panel(i + 1, row)
            self.console.print(record_panel)

    def _build_single_record_panel(self, index: int, row: aiosqlite.Row) -> Panel:
        """为单条记录构建一个包含所有信息的、结构化的 Rich Panel。"""
        status_colors = {
            "TRANSLATED": "green",
            "APPROVED": "bright_green",
            "PENDING": "yellow",
            "TRANSLATING": "cyan",
            "FAILED": "red",
        }
        status_color = status_colors.get(row["status"], "default")
        main_table = Table(box=None, show_header=False, padding=(0, 1))
        main_table.add_column(style="dim", width=12)
        main_table.add_column(style="bold")
        main_table.add_row("原文:", f"'{row['original_content']}'")
        if row["translation_content"]:
            main_table.add_row("译文:", f"'{row['translation_content']}'")
        meta_text = Text.from_markup(
            f"[dim]引擎:[/] {row['engine']} (v{row['engine_version']})  [dim]更新于:[/] {row['last_updated_at']}"
        )
        if row["business_id"]:
            meta_text.append(
                f"\n[dim]业务 ID:[/] [cyan]{row['business_id']}[/cyan]  [dim]最后请求于:[/] {row['last_requested_at']}"
            )
        context_panel: Optional[Panel] = None
        if row["context_json"]:
            try:
                parsed_context = json.loads(row["context_json"])
                context_str = json.dumps(parsed_context, indent=2, ensure_ascii=False)
                syntax = Syntax(context_str, "json", theme="monokai", line_numbers=True)
                context_panel = Panel(
                    syntax,
                    title="[dim]关联上下文[/dim]",
                    border_style="blue",
                    title_align="left",
                )
            except json.JSONDecodeError:
                context_panel = Panel(
                    row["context_json"],
                    title="[dim]关联上下文 (原始文本)[/dim]",
                    border_style="red",
                    title_align="left",
                )

        # --- 核心修复：过滤掉 None 值，确保类型安全 ---
        render_group_items: list[RenderableType] = [
            item for item in [main_table, meta_text, context_panel] if item is not None
        ]
        render_group = Group(*render_group_items)

        return Panel(
            render_group,
            title=f"[bold]记录 #{index}[/bold] (ID: {row['translation_id']})",
            subtitle=Text.from_markup(
                f"状态: [{status_color}]{row['status']}[/{status_color}] | 目标: [magenta]{row['lang_code']}[/magenta]"
            ),
            border_style="bright_blue",
            padding=(1, 2),
        )


def main() -> None:
    """命令行接口的主入口点。"""
    setup_logging(log_level="WARNING")
    console = Console(stderr=True)

    parser = argparse.ArgumentParser(
        description="一个用于检查和解读 Trans-Hub (v3.2+) 数据库内容的专业工具。",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "db_path",
        type=str,
        help="要检查的 Trans-Hub SQLite 数据库文件的路径。\n示例: poetry run python tools/inspect_db.py transhub.db",
    )
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    try:
        inspector = DatabaseInspector(args.db_path, console)
        asyncio.run(inspector.inspect())
    except Exception:
        console.print("[bold red]执行过程中发生意外错误：[/bold red]")
        # --- 核心升级：使用 Rich 打印漂亮的 Traceback ---
        console.print_exception(show_locals=True, width=console.width)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]操作被用户中断。[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
