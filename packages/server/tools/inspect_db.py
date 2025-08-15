# packages/server/tools/inspect_db.py
"""
一个专业的命令行工具，用于检查和解读 Trans-Hub (v2.5.1+) 数据库的内容。
"""

import json

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThTransHead,
    ThTransRev,
)

console = Console()

STATUS_STYLES = {
    "published": "bold green",
    "reviewed": "bold cyan",
    "draft": "bold yellow",
    "rejected": "bold red",
}


def inspect_database(db_url: str):
    """主检查函数。"""
    sync_db_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    engine = create_engine(sync_db_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        console.print(
            Panel(
                f"🔍 正在检查数据库: [yellow]{sync_db_url}[/yellow]",
                border_style="blue",
            )
        )

        content_items = session.query(ThContent).order_by(ThContent.created_at).all()
        if not content_items:
            console.print("[yellow]数据库中没有内容条目。[/yellow]")
            return

        for content in content_items:
            _render_content_panel(session, content)


def _render_content_panel(session, content: ThContent):
    """渲染单个内容条目及其所有关联信息。"""
    uida_table = Table(
        box=None, show_header=False, padding=(0, 1), title="[bold]UIDA & Source[/bold]"
    )
    uida_table.add_column(style="dim cyan", width=12)
    uida_table.add_column()
    uida_table.add_row("Project ID:", content.project_id)
    uida_table.add_row("Namespace:", content.namespace)
    uida_table.add_row(
        "Source:",
        Syntax(
            json.dumps(content.source_payload_json, indent=2), "json", theme="monokai"
        ),
    )
    uida_table.add_row(
        "Keys:",
        Syntax(json.dumps(content.keys_json, indent=2), "json", theme="monokai"),
    )

    heads = (
        session.query(ThTransHead)
        .filter_by(content_id=content.id)
        .order_by(ThTransHead.target_lang)
        .all()
    )

    console.print(
        Panel(
            uida_table,
            title=f"📦 [cyan]Content ID[/cyan]: {content.id}",
            border_style="cyan",
            expand=False,
        )
    )

    if not heads:
        console.print("  [dim]此内容尚无翻译记录。[/dim]")

    for head in heads:
        _render_head_panel(session, head)


def _render_head_panel(session, head: ThTransHead):
    """渲染单个翻译头及其修订、评论和事件。"""
    revs = (
        session.query(ThTransRev)
        .filter(
            ThTransRev.project_id == head.project_id,
            ThTransRev.content_id == head.content_id,
            ThTransRev.target_lang == head.target_lang,
            ThTransRev.variant_key == head.variant_key,
        )
        .order_by(ThTransRev.revision_no.desc())
        .all()
    )

    rev_table = Table(
        title="[bold]Revisions[/bold]", show_header=True, header_style="bold blue"
    )
    rev_table.add_column("Rev#", justify="right")
    rev_table.add_column("Status")
    rev_table.add_column("Translated Text")
    rev_table.add_column("Rev ID")
    rev_table.add_column("Pointer")

    for rev in revs:
        pointers = []
        if rev.id == head.current_rev_id:
            pointers.append("[cyan]HEAD[/cyan]")
        if rev.id == head.published_rev_id:
            pointers.append("[green]LIVE[/green]")
        status_style = STATUS_STYLES.get(rev.status, "default")
        text = (
            rev.translated_payload_json.get("text", "[dim]N/A[/dim]")
            if rev.translated_payload_json
            else "[dim]N/A[/dim]"
        )
        rev_table.add_row(
            str(rev.revision_no),
            f"[{status_style}]{rev.status.upper()}[/]",
            text,
            rev.id[:8],
            " ".join(pointers),
        )

    # ... Add similar tables for comments and events ...

    console.print(
        Panel(
            rev_table,  # In a real impl, group rev_table, comment_table, event_table
            title=f"🗣️  [magenta]Head[/magenta]: {head.id[:8]} ([bold]{head.target_lang}[/bold] / {head.variant_key})",
            border_style="magenta",
            expand=False,
        )
    )


if __name__ == "__main__":
    config = TransHubConfig()
    inspect_database(config.database.url)
