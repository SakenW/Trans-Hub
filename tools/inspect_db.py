# tools/inspect_db.py
"""一个专业的命令行工具，用于检查和解读 Trans-Hub (v3.2+) 数据库的内容。"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

# v3.7 修复：将 sys.path 修改逻辑置于顶部，并添加 noqa
try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from trans_hub.logging_config import setup_logging  # noqa: E402
except (ImportError, IndexError):
    print("错误: 无法将项目根目录添加到 sys.path。请确保此脚本位于 'tools' 目录下。")
    sys.exit(1)

import aiosqlite  # noqa: E402
import structlog  # noqa: E402
from rich.console import Console, Group  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

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
        # v3.7 修复：更新 SQL 查询以匹配 v3.0 Schema
        query = """
        SELECT
            t.id AS translation_id,
            t.lang_code,
            t.status,
            t.translation_payload_json,
            t.engine,
            t.engine_version,
            t.last_updated_at,
            c.source_payload_json,
            ctx.context_payload_json,
            c.business_id,
            j.last_requested_at
        FROM th_translations t
        JOIN th_content c ON t.content_id = c.id
        LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
        LEFT JOIN th_jobs j ON t.content_id = j.content_id
        ORDER BY t.last_updated_at DESC;
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
            "TRANSLATED": "green", "APPROVED": "bright_green",
            "PENDING": "yellow", "TRANSLATING": "cyan", "FAILED": "red",
        }
        status_color = status_colors.get(row["status"], "default")

        # --- 主要内容 ---
        original_payload = json.loads(row["source_payload_json"])
        original_text = original_payload.get("text", str(original_payload))
        
        translated_text = "[dim]N/A[/dim]"
        if row["translation_payload_json"]:
            translated_payload = json.loads(row["translation_payload_json"])
            translated_text = translated_payload.get("text", str(translated_payload))

        content_table = Table(box=None, show_header=False, padding=(0, 1))
        content_table.add_column(style="dim", width=12)
        content_table.add_column()
        content_table.add_row("原文:", f"[cyan]{original_text}[/cyan]")
        content_table.add_row("译文:", f"[cyan]{translated_text}[/cyan]")
        
        # --- 元数据 ---
        meta_table = Table(show_header=False, box=None, padding=(0, 1))
        meta_table.add_column(style="dim", width=12)
        meta_table.add_column()
        if row["business_id"]:
            meta_table.add_row("业务 ID:", f"[blue]{row['business_id']}[/blue]")
        meta_table.add_row("更新于:", row['last_updated_at'].split('.')[0])
        meta_table.add_row("引擎:", f"{row['engine']} [dim](v{row['engine_version']})[/dim]")

        # --- 上下文 ---
        context_renderable = None
        if row["context_payload_json"]:
            try:
                parsed = json.loads(row["context_payload_json"])
                pretty_json = json.dumps(parsed, indent=2, ensure_ascii=False)
                context_renderable = Syntax(pretty_json, "json", theme="monokai")
            except json.JSONDecodeError:
                context_renderable = Text(row["context_payload_json"])

        renderables = [content_table, meta_table]
        if context_renderable:
            renderables.append(Panel(
                context_renderable, title="[dim]关联上下文[/dim]",
                border_style="dim", title_align="left"
            ))

        render_group = Group(*renderables)
        
        title = Text.from_markup(
            f"记录 #{index} | 状态: [{status_color}]{row['status']}[/{status_color}] | "
            f"目标: [magenta]{row['lang_code']}[/magenta]"
        )
        subtitle = Text.from_markup(f"[dim]ID: {row['translation_id']}[/dim]")

        return Panel(
            render_group, title=title, subtitle=subtitle,
            border_style="bright_blue", padding=(1, 2), subtitle_align="right"
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
        console.print_exception(show_locals=True, width=console.width)
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]操作被用户中断。[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
