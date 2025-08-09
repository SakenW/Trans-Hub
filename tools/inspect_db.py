# tools/inspect_db.py
# [v4.0 UIDA 版]
"""一个专业的命令行工具，用于检查和解读 Trans-Hub (v3.0+) 数据库的内容。"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

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

from rich.console import Console, Group, RenderableType  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

log = structlog.get_logger(__name__)


class DatabaseInspector:
    """封装了检查 Trans-Hub 数据库所有逻辑的类。"""

    def __init__(self, db_path: str, console: Console):
        self.db_path = db_path
        self.console = console
        self.conn: aiosqlite.Connection | None = None

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
            Panel("[bold cyan]Trans-Hub 数据库统计概览 (UIDA v1.2 Schema)[/bold cyan]", expand=False)
        )
        queries = {
            "源内容 (th_content)": "SELECT COUNT(*) FROM th_content;",
            "翻译记录 (th_translations)": "SELECT COUNT(*) FROM th_translations;",
            "翻译记忆 (th_tm)": "SELECT COUNT(*) FROM th_tm;",
            "TM 追溯链接 (th_tm_links)": "SELECT COUNT(*) FROM th_tm_links;",
            "草稿 (draft)": "SELECT COUNT(*) FROM th_translations WHERE status = 'draft';",
            "待审 (reviewed)": "SELECT COUNT(*) FROM th_translations WHERE status = 'reviewed';",
            "已发布 (published)": "SELECT COUNT(*) FROM th_translations WHERE status = 'published';",
            "已拒绝 (rejected)": "SELECT COUNT(*) FROM th_translations WHERE status = 'rejected';",
            "语言回退策略 (th_locales_fallbacks)": "SELECT COUNT(*) FROM th_locales_fallbacks;",
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
                t.id AS translation_id,
                t.target_lang,
                t.variant_key,
                t.status,
                t.revision,
                t.translated_payload_json,
                t.engine_name,
                t.updated_at,
                c.project_id,
                c.namespace,
                c.keys_json_debug,
                c.source_payload_json
            FROM th_translations t
            JOIN th_content c ON t.content_id = c.id
            ORDER BY c.project_id, c.namespace, t.target_lang, t.updated_at DESC;
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
            "published": "green",
            "reviewed": "cyan",
            "draft": "yellow",
            "rejected": "red",
        }
        status_color = status_colors.get(row["status"], "default")

        # --- UIDA 信息 ---
        uida_table = Table(box=None, show_header=False, padding=(0, 1))
        uida_table.add_column(style="dim", width=12)
        uida_table.add_column(style="bright_white")
        uida_table.add_row("Project ID:", row["project_id"])
        uida_table.add_row("Namespace:", row["namespace"])

        # --- 主要内容 ---
        source_payload = json.loads(row["source_payload_json"])
        source_text = source_payload.get("text", str(source_payload))
        translated_text = "[dim]N/A[/dim]"
        if row["translated_payload_json"]:
            translated_payload = json.loads(row["translated_payload_json"])
            translated_text = translated_payload.get("text", str(translated_payload))
        
        content_table = Table(box=None, show_header=False, padding=(0, 1))
        content_table.add_column(style="dim", width=12)
        content_table.add_column()
        content_table.add_row("原文:", f"[cyan]{source_text}[/cyan]")
        content_table.add_row("译文:", f"[cyan]{translated_text}[/cyan]")

        # --- Keys & 元数据 ---
        keys_renderable: RenderableType
        try:
            parsed_keys = json.loads(row["keys_json_debug"])
            pretty_json = json.dumps(parsed_keys, indent=2, ensure_ascii=False)
            keys_renderable = Syntax(pretty_json, "json", theme="monokai", word_wrap=True)
        except (json.JSONDecodeError, TypeError):
            keys_renderable = Text(row["keys_json_debug"] or "[dim]N/A[/dim]")
        
        keys_panel = Panel(
            keys_renderable,
            title="[dim]UIDA Keys[/dim]",
            border_style="dim",
            title_align="left",
            expand=False,
        )

        meta_table = Table(show_header=False, box=None, padding=(0, 1))
        meta_table.add_column(style="dim", width=12)
        meta_table.add_column()
        meta_table.add_row("Variant Key:", f"[blue]{row['variant_key']}[/blue]")
        meta_table.add_row("Revision:", str(row["revision"]))
        meta_table.add_row("更新于:", str(row["updated_at"]).split(".")[0])
        if row["engine_name"]:
            meta_table.add_row("引擎:", row["engine_name"])

        renderables = Group(uida_table, content_table, keys_panel, meta_table)

        title = Text.from_markup(
            f"记录 #{index} | 状态: [{status_color}]{row['status'].upper()}[/{status_color}] | "
            f"目标: [magenta]{row['target_lang']}[/magenta]"
        )
        subtitle = Text.from_markup(f"[dim]Translation ID: {row['translation_id']}[/dim]")

        return Panel(
            renderables,
            title=title,
            subtitle=subtitle,
            border_style="bright_blue",
            padding=(1, 2),
            subtitle_align="right",
        )


def main() -> None:
    """命令行接口的主入口点。"""
    setup_logging(log_level="WARNING")
    console = Console(stderr=True)

    parser = argparse.ArgumentParser(
        description="一个用于检查和解读 Trans-Hub (v3.0+) 数据库内容的专业工具。",
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