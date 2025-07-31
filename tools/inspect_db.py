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
        # 状态符号映射
        status_symbols = {
            "TRANSLATED": "✔",
            "APPROVED": "✔",
            "PENDING": "⏳",
            "TRANSLATING": "⏳",
            "FAILED": "✖",
        }
        # 状态颜色映射
        status_colors = {
            "TRANSLATED": "green",
            "APPROVED": "bright_green",
            "PENDING": "yellow",
            "TRANSLATING": "cyan",
            "FAILED": "red",
        }
        
        status_symbol = status_symbols.get(row["status"], "?" )
        status_color = status_colors.get(row["status"], "default")
        
        # 主要内容表格 (原文/译文)
        content_table = Table(box=None, show_header=False, padding=(0, 1))
        content_table.add_column(style="dim", width=12)
        content_table.add_column()
        
        # 原文和译文使用青色显示
        content_table.add_row("原文:", f"[cyan]{row['original_content']}[/cyan]")
        if row["translation_content"]:
            content_table.add_row("译文:", f"[cyan]{row['translation_content']}[/cyan]")
        
        # 元数据表格
        meta_table = Table(show_header=False, box=None, padding=(0, 1))
        meta_table.add_column(style="dim", width=12)
        meta_table.add_column()
        
        # 业务ID使用蓝色显示
        if row["business_id"]:
            meta_table.add_row("业务 :", f"[blue]{row['business_id']}[/blue]")
        
        # 时间格式化函数
        from datetime import datetime
        
        def format_timestamp(ts_str: str) -> str:
            try:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                return ts_str
        
        # 时间信息
        formatted_updated_at = format_timestamp(row['last_updated_at'])
        meta_table.add_row("时间 :", formatted_updated_at)
        
        # 引擎信息，版本号使用灰色显示
        meta_table.add_row("引擎 :", f"{row['engine']} [dim](v{row['engine_version']})[/dim]")
        
        # 使用 Group 组织内容
        renderables: list[RenderableType] = [content_table, meta_table]
        
        # 上下文面板 (如果存在)
        context_panel: Optional[Panel] = None
        if row["context_json"]:
            try:
                parsed_context = json.loads(row["context_json"])
                context_str = json.dumps(parsed_context, indent=2, ensure_ascii=False)
                syntax = Syntax(context_str, "json", theme="monokai", line_numbers=False)
                context_panel = Panel(
                    syntax,
                    title="[dim]▼ 关联上下文[/dim]",
                    border_style="dim",
                    title_align="left",
                    padding=(0, 1),
                )
                renderables.append(context_panel)
            except json.JSONDecodeError:
                context_panel = Panel(
                    row["context_json"],
                    title="[dim]▼ 关联上下文 (原始文本)[/dim]",
                    border_style="red",
                    title_align="left",
                    padding=(0, 1),
                )
                renderables.append(context_panel)
        
        # 原文和译文框线面板
        original_panel = Panel(
            f"[cyan]{row['original_content']}[/cyan]",
            title="[dim]原文[/dim]",
            border_style="dim",
            title_align="left",
            padding=(0, 1),
        )
        
        translation_panel = None
        if row["translation_content"]:
            translation_panel = Panel(
                f"[cyan]{row['translation_content']}[/cyan]",
                title="[dim]译文[/dim]",
                border_style="dim",
                title_align="left",
                padding=(0, 1),
            )
        
        # 构建最终显示组
        final_renderables: list[RenderableType] = [
            Text.from_markup(f"[green]{status_symbol} 记录 #{index}[/green] [dim]|[/dim] 状态: [{status_color}]{row['status']}[/{status_color}] [dim]|[/dim] 目标: [magenta]{row['lang_code']}[/magenta]"),
            Text(""),  # 空行
            Text.from_markup(f"[yellow]ID :[/yellow] [blue]{row['translation_id']}[/blue]"),
        ]
        
        if row["business_id"]:
            final_renderables.append(Text.from_markup(f"[yellow]业务 :[/yellow] [blue]{row['business_id']}[/blue]"))
        
        final_renderables.extend([
            Text.from_markup(f"[yellow]时间 :[/yellow] {formatted_updated_at}"),
            Text.from_markup(f"[yellow]引擎 :[/yellow] {row['engine']} [dim](v{row['engine_version']})[/dim]"),
            Text(""),  # 空行
            original_panel,
        ])
        
        if translation_panel:
            final_renderables.append(translation_panel)
        
        if context_panel:
            final_renderables.append(Text(""))  # 空行
            final_renderables.append(context_panel)
        
        render_group = Group(*final_renderables)
        
        return Panel(
            render_group,
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
