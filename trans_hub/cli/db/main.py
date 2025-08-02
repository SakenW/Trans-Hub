# trans_hub/cli/db/main.py
"""
Trans-Hub Database CLI 子模块。
"""

import os
from pathlib import Path

import structlog
from rich.console import Console

from trans_hub.db.schema_manager import apply_migrations
from trans_hub.utils import get_database_url

log = structlog.get_logger("trans_hub.cli.db")
console = Console()


def db_migrate(database_url: str = "") -> None:
    """
    执行数据库迁移。
    """
    # 如果没有提供数据库URL，则从配置中获取
    if not database_url:
        database_url = get_database_url()

    # 检查是否为SQLite数据库
    if not database_url.startswith("sqlite:///"):
        console.print("[red]仅支持 SQLite 数据库的迁移。[/red]")
        raise SystemExit(1)

    # 提取数据库路径
    if database_url.startswith("sqlite:///"):
        db_path = database_url[10:]  # 去掉 "sqlite:///" 前缀
    elif database_url.startswith("sqlite://"):
        db_path = database_url[9:]  # 处理 sqlite:// 格式（无第三个斜杠）
    else:
        db_path = database_url

    if db_path != ":memory:":
        try:
            db_path = os.path.abspath(db_path)
            console.print(f"[blue]正在对数据库应用迁移:[/blue] {db_path}")
            # 确保父目录存在
            parent_dir = Path(db_path).parent
            console.print(f"[blue]正在创建数据库目录:[/blue] {parent_dir}")
            parent_dir.mkdir(parents=True, exist_ok=True)
            console.print("[green]✅ 数据库目录创建成功[/green]")
        except Exception as e:
            console.print(f"[red]❌ 无法创建数据库目录: {e}[/red]")
            raise SystemExit(1)

    try:
        # 运行迁移
        console.print("[blue]正在应用数据库迁移...[/blue]")
        apply_migrations(db_path)
        console.print("[green]✅ 数据库迁移成功完成！[/green]")
    except Exception as e:
        log.error("数据库迁移失败", error=str(e), exc_info=True)
        console.print(f"[red]❌ 数据库迁移失败: {e}[/red]")
        console.print("[red]详细错误信息:[/red]")
        import traceback

        console.print(f"[red]{traceback.format_exc()}[/red]")
        raise SystemExit(1)
