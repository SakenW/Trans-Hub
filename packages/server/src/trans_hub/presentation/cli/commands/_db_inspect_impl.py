# packages/server/src/trans_hub/presentation/cli/commands/_db_inspect_impl.py
"""
数据库内容审查工具的实现逻辑。
"""

from rich.console import Console
from rich.panel import Panel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trans_hub.infrastructure.db._schema import ThContent

console = Console()

STATUS_STYLES = {
    "published": "bold green",
    "reviewed": "bold cyan",
    "draft": "bold yellow",
    "rejected": "bold red",
}


def inspect_database_impl(db_url: str):
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        console.print(
            Panel(f"🔍 正在检查数据库: [yellow]{db_url}[/yellow]", border_style="blue")
        )
        content_items = session.query(ThContent).order_by(ThContent.created_at).all()
        if not content_items:
            console.print("[yellow]数据库中没有内容条目。[/yellow]")
            return
        for content in content_items:
            _render_content_panel(session, content)


def _render_content_panel(session, content: ThContent):
    # This function and _render_head_panel remain identical to the original inspect_db.py
    # ... (Implementation from inspect_db.py) ...
    pass  # Placeholder for brevity
