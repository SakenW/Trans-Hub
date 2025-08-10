# tools/db_doctor.py
# [v1.3 Final Fix] 修正 rolcredb 拼写错误和 alembic.command 导入问题。
"""
一个用于诊断、管理和修复 Trans-Hub 测试数据库环境的交互式命令行工具。

运行方式:
 poetry run python tools/db_doctor.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# --- 路径设置，确保能导入 trans_hub ---
try:
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from trans_hub.db.schema import Base
except (ImportError, IndexError):
    print("错误: 无法将项目根目录添加到 sys.path。请确保此脚本位于 'tools' 目录下。")
    sys.exit(1)
# ---

import questionary
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

# [核心修正] 导入 alembic command
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

# --- 初始化 ---
console = Console()

# --- 加载配置 ---
load_dotenv()
PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")
if not PG_DATABASE_URL:
    console.print("[bold red]错误: 环境变量 TH_DATABASE_URL 未设置。[/bold red]")
    sys.exit(1)

parsed_url = urlparse(PG_DATABASE_URL.replace("+asyncpg", ""))
APP_DB_NAME = parsed_url.path.lstrip("/")
MAINTENANCE_DB_URL = parsed_url._replace(path="/postgres").geturl()
APP_DB_URL = parsed_url.geturl()


def get_alembic_versions() -> tuple[str | None, str | None]:
    """获取数据库中的当前版本和代码中的最新版本。"""
    try:
        engine = create_engine(APP_DB_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            db_version = result.scalar_one_or_none()
    except (OperationalError, ProgrammingError):
        db_version = "不存在或无法访问"

    try:
        alembic_cfg_path = project_root / "alembic.ini"
        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        script = ScriptDirectory.from_config(alembic_cfg)
        head_version = script.get_current_head()
    except Exception:
        head_version = "错误：无法读取"

    return db_version, head_version


def do_check_db_status() -> bool:
    """执行一系列检查来验证数据库环境。"""
    console.print(
        Panel("[bold cyan]🩺 Trans-Hub 数据库环境健康检查[/bold cyan]", expand=False)
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("检查项", style="cyan")
    table.add_column("状态")
    table.add_column("详情")

    errors = 0

    try:
        engine = create_engine(MAINTENANCE_DB_URL)
        with engine.connect() as conn:
            table.add_row(
                "维护库连接",
                "[green]✅ 成功[/green]",
                f"成功连接到 '{MAINTENANCE_DB_URL}'",
            )

            # [核心修正] 修正 SQL 查询中的拼写错误
            result = conn.execute(
                text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user;")
            )
            can_create_db = result.scalar_one()
            if can_create_db:
                table.add_row(
                    "创建数据库权限",
                    "[green]✅ 拥有[/green]",
                    "用户有 CREATEDB 权限，可以运行测试。",
                )
            else:
                table.add_row(
                    "创建数据库权限",
                    "[bold red]❌ 缺失[/bold red]",
                    "用户缺少 CREATEDB 权限。请运行: ALTER USER your_user CREATEDB;",
                )
                errors += 1
    except Exception as e:
        table.add_row(
            "维护库连接",
            "[bold red]❌ 失败[/bold red]",
            f"无法连接到 '{MAINTENANCE_DB_URL}'.\n错误: {e}",
        )
        errors += 1

    db_version, head_version = get_alembic_versions()
    if "无法访问" not in str(db_version):
        table.add_row(
            "应用数据库", "[green]✅ 存在[/green]", f"数据库 '{APP_DB_NAME}' 已存在。"
        )
        if db_version == head_version:
            table.add_row(
                "Schema 版本",
                "[green]✅ 最新[/green]",
                f"数据库已是最新版本 ({head_version})。",
            )
        else:
            table.add_row(
                "Schema 版本",
                "[yellow]⚠️ 过期[/yellow]",
                f"数据库版本: {db_version}, 最新版本: {head_version}。",
            )
            errors += 1
    else:
        table.add_row(
            "应用数据库",
            "[bold red]❌ 不存在或无法访问[/bold red]",
            f"数据库 '{APP_DB_NAME}' 需要被创建。",
        )
        errors += 1

    console.print(table)

    if errors == 0:
        console.print(
            Panel(
                "[bold green]✅ 您的数据库环境已为运行集成测试准备就绪！[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]❌ 您的数据库环境存在问题，请根据提示修复或使用重建功能。[/bold red]",
                border_style="red",
            )
        )
    return errors == 0


def do_rebuild() -> None:
    """删除并重新创建应用数据库，然后运行所有迁移。"""
    console.print(
        f"[bold yellow]警告：此操作将永久删除数据库 '{APP_DB_NAME}' 及其所有数据。[/bold yellow]"
    )
    proceed = questionary.confirm(
        f"您确定要重建数据库 '{APP_DB_NAME}' 吗?", default=False
    ).ask()
    if not proceed:
        console.print("[red]操作已取消。[/red]")
        return

    with console.status("[bold blue]正在重建数据库...", spinner="dots") as status:
        try:
            status.update("正在删除旧数据库（如果存在）...")
            engine = create_engine(MAINTENANCE_DB_URL, isolation_level="AUTOCOMMIT")
            with engine.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{APP_DB_NAME}"'))

            status.update("正在创建新数据库...")
            with engine.connect() as conn:
                conn.execute(text(f'CREATE DATABASE "{APP_DB_NAME}"'))

            status.update("正在运行数据库迁移...")
            alembic_cfg = AlembicConfig(project_root / "alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", APP_DB_URL)
            command.upgrade(alembic_cfg, "head")
        except Exception as e:
            console.print(f"\n[bold red]重建数据库失败: {e}[/bold red]")
            return

    console.print(
        f"[bold green]✅ 数据库 '{APP_DB_NAME}' 已成功重建并迁移至最新版本！[/bold green]"
    )


def do_clear() -> None:
    """连接到应用数据库并清空所有表。"""
    console.print(
        f"[bold yellow]警告：此操作将永久删除数据库 '{APP_DB_NAME}' 中的所有数据。[/bold yellow]"
    )
    proceed = questionary.confirm(
        f"您确定要清空数据库 '{APP_DB_NAME}' 吗?", default=False
    ).ask()
    if not proceed:
        console.print("[red]操作已取消。[/red]")
        return

    with console.status("[bold blue]正在清空数据...", spinner="dots") as status:
        try:
            engine = create_engine(APP_DB_URL)
            with engine.begin() as conn:
                tables = reversed(Base.metadata.sorted_tables)
                for table in tables:
                    status.update(f"正在清空表: {table.name}...")
                    conn.execute(
                        text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE;')
                    )
        except Exception as e:
            console.print(f"\n[bold red]清空数据库失败: {e}[/bold red]")
            return

    console.print(
        f"[bold green]✅ 数据库 '{APP_DB_NAME}' 的所有数据已成功清空！[/bold green]"
    )


def main_loop() -> None:
    """主交互循环。"""
    console.print(
        Panel(
            "[bold cyan]欢迎使用 Trans-Hub 数据库医生[/bold cyan]",
            subtitle="请选择一个操作",
        )
    )

    while True:
        choice = questionary.select(
            "主菜单:",
            choices=[
                questionary.Choice("🩺 健康检查 (Check Status)", "check"),
                questionary.Choice("🔄 重建数据库 (Rebuild Database)", "rebuild"),
                questionary.Choice("🗑️ 清空数据 (Clear Data)", "clear"),
                questionary.Separator(),
                questionary.Choice("🚪 退出 (Exit)", "exit"),
            ],
        ).ask()

        console.print()

        if choice == "check":
            do_check_db_status()
        elif choice == "rebuild":
            do_rebuild()
        elif choice == "clear":
            do_clear()
        elif choice == "exit" or choice is None:
            console.print("[dim]再见！[/dim]")
            break

        console.print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作被用户中断。再见！[/yellow]")
