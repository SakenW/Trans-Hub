# packages/server/src/trans_hub/management/db_service.py
"""
提供用于数据库管理和诊断的服务。
这是所有数据库运维操作的核心逻辑封装，属于项目的“管理平面”。
"""

from __future__ import annotations

import os
import sys
import json
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from sqlalchemy import create_engine, text, Engine, inspect
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.util import CommandError  # [新增] 用于捕获 Alembic 自己的错误

from trans_hub.infrastructure.db._schema import Base, ThContent, ThTransHead, ThTransRev
from trans_hub.config import TransHubConfig

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

# --- 可选依赖处理 ---
try:
    import questionary
except ImportError:
    questionary = None

console = Console()

STATUS_STYLES = {
    "published": "bold green",
    "reviewed": "bold cyan",
    "draft": "bold yellow",
    "rejected": "bold red",
}


class DbService:
    """封装了数据库诊断、迁移、修复和审查的所有操作。"""

    def __init__(self, config: TransHubConfig, alembic_ini_path: str):
        self.config = config
        self.alembic_ini_path = alembic_ini_path
        self.is_prod = os.getenv("TRANSHUB_ENV") == "production"

        app_url_obj = make_url(self.config.database.url)
        self.app_db_name = app_url_obj.database
        self.sync_app_url: URL = self._to_sync_url(app_url_obj)

        maint_url_str = self.config.maintenance_database_url
        if not maint_url_str:
            raise ValueError(
                "维护数据库 URL (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置。"
            )
        self.sync_maint_url: URL = self._to_sync_url(make_url(maint_url_str))

    @staticmethod
    def _to_sync_url(url: URL) -> URL:
        if not url.drivername.startswith("postgresql"):
            raise TypeError("数据库医生目前仅支持 PostgreSQL。")
        return url.set(drivername="postgresql+psycopg")

    @staticmethod
    def _create_sync_engine(url: URL) -> Engine:
        """创建带有统一 search_path 的同步引擎。"""
        return create_engine(
            url,
            connect_args={"options": "-c search_path=th,public"},
        )

    @staticmethod
    def _create_sync_engine_autocommit(url: URL) -> Engine:
        """创建带有统一 search_path 且自动提交的同步引擎。"""
        return create_engine(
            url,
            connect_args={"options": "-c search_path=th,public"},
            isolation_level="AUTOCOMMIT",
        )

    def _get_alembic_cfg(self) -> AlembicConfig:
        cfg = AlembicConfig(self.alembic_ini_path)
        real_url = self.sync_app_url.render_as_string(hide_password=False)
        safe_url = real_url.replace("%", "%%")
        cfg.set_main_option("sqlalchemy.url", safe_url)
        return cfg

    # --- 医生 (Doctor) 功能 ---

    def _run_deep_structure_probe(self, engine: Engine, table: Table):
        """运行深度结构探测。"""
        try:
            inspector = inspect(engine)
            schemas = inspector.get_schema_names()
            table.add_row("探测到的 Schemas", f"{schemas}")

            if "th" in schemas:
                th_tables = inspector.get_table_names(schema="th")
                table.add_row(
                    "`th` schema下的表", f"{th_tables if th_tables else '[空]'}"
                )
                if "alembic_version" in th_tables:
                    table.add_row("`th.alembic_version`", "[green]✅ 物理存在[/green]")
                else:
                    table.add_row("`th.alembic_version`", "[red]❌ 物理不存在[/red]")
            else:
                table.add_row("`th` schema", "[red]❌ 不存在[/red]")
        except Exception as e:
            table.add_row("深度探测", f"[red]❌ 失败: {e}[/red]")

    def check_status(self, deep: bool = False) -> bool:
        """执行全面的数据库健康检查。"""
        console.print(Panel("🩺 数据库健康检查", border_style="cyan"))
        errors = 0
        table = Table(show_header=False, box=None)
        table.add_column(style="cyan", width=25)
        table.add_column()

        try:
            engine = self._create_sync_engine(self.sync_maint_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                table.add_row("维护库连接", "[green]✅ 成功[/green]")
        except Exception as e:
            table.add_row("维护库连接", f"[red]❌ 失败: {e}[/red]")
            errors += 1
        finally:
            if "engine" in locals():
                engine.dispose()

        db_version = "无法访问"
        engine = self._create_sync_engine(self.sync_app_url)
        try:
            with engine.connect() as conn:
                table.add_row("应用库连接", "[green]✅ 成功[/green]")
                if deep:
                    self._run_deep_structure_probe(engine, table)

                try:
                    res = conn.execute(
                        text("SELECT version_num FROM th.alembic_version")
                    )
                    db_version = res.scalar_one_or_none() or "[空]"
                except ProgrammingError:
                    db_version = "[表不存在]"
        except Exception as e:
            table.add_row("应用库连接", f"[red]❌ 失败: {e}[/red]")
            errors += 1
        finally:
            engine.dispose()

        head_version = "无法获取"
        try:
            script = ScriptDirectory.from_config(self._get_alembic_cfg())
            head_version = script.get_current_head() or "[无]"
        except Exception:
            errors += 1

        table.add_row("数据库 Alembic 版本", db_version)
        table.add_row("代码 Alembic Head 版本", head_version)
        if db_version == head_version and not db_version.startswith("["):
            table.add_row("版本一致性", "[green]✅ 一致[/green]")
        else:
            table.add_row("版本一致性", "[yellow]⚠️ 不一致或未迁移[/yellow]")
            errors += 1

        console.print(table)
        return errors == 0

    def run_migrations(self, force: bool = False) -> None:
        """运行数据库迁移，可选强制兜底。"""
        console.print(Panel("🚀 数据库迁移 (Upgrade to Head)", border_style="cyan"))
        alembic_cfg = self._get_alembic_cfg()
        try:
            console.print("正在尝试标准 Alembic 迁移...")
            command.upgrade(alembic_cfg, "head")
            console.print("[bold green]✅ 标准迁移成功！[/bold green]")
        except Exception as e:
            if not force:
                console.print(f"[bold red]❌ 标准迁移失败: {e}[/bold red]")
                console.print("提示: 可尝试使用 --force 标志启用兜底模式。")
                sys.exit(1)

            console.print(
                f"[bold yellow]⚠️ 标准迁移失败: {e}。正在启动强制兜底模式...[/bold yellow]"
            )
            self._fallback_migration(alembic_cfg)

    def _fallback_migration(self, alembic_cfg: AlembicConfig) -> None:
        """兜底迁移：直接使用 ORM 创建所有表，并手动写入版本号。"""
        try:
            engine = self._create_sync_engine(self.sync_app_url)
            with engine.begin() as conn:
                console.print("  - 正在执行 `Base.metadata.create_all()`...")
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
                Base.metadata.create_all(bind=conn)
                console.print("  - ORM 表结构创建完成。")

                head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
                if head:
                    conn.execute(text("DROP TABLE IF EXISTS th.alembic_version"))
                    conn.execute(
                        text(
                            "CREATE TABLE th.alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                        )
                    )
                    conn.execute(
                        text(
                            "INSERT INTO th.alembic_version (version_num) VALUES (:v)"
                        ),
                        {"v": head},
                    )
                    console.print(
                        f"  - 已强制写入 Alembic 版本: [yellow]{head}[/yellow]"
                    )
            console.print("[bold green]✅ 兜底迁移成功！[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ 兜底迁移失败: {e}[/bold red]")
            sys.exit(1)

    def stamp_version(self, revision: str) -> None:
        """将数据库的 Alembic 版本标记为指定版本，而不运行迁移。"""
        console.print(
            Panel(
                f"标记数据库版本为: [yellow]{revision}[/yellow]", border_style="yellow"
            )
        )
        alembic_cfg = self._get_alembic_cfg()
        try:
            command.stamp(alembic_cfg, revision)
            console.print("[bold green]✅ 标记成功！[/bold green]")
        except CommandError as e:
            console.print(f"[bold red]❌ 标记失败: {e}[/bold red]")
            sys.exit(1)

    def rebuild_database(self) -> None:
        """[危险] 删除并重建数据库。"""
        if self.is_prod:
            console.print(
                "[bold red]❌ 操作被阻止: 禁止在生产环境中重建数据库。[/bold red]"
            )
            return

        console.print(Panel(f"重建数据库: {self.app_db_name}", border_style="red"))
        engine = self._create_sync_engine_autocommit(self.sync_maint_url)
        try:
            with engine.connect() as conn:
                console.print(f"  - 正在终止到 '{self.app_db_name}' 的所有连接...")
                conn.execute(
                    text(f'DROP DATABASE IF EXISTS "{self.app_db_name}" WITH (FORCE)')
                )
                console.print(f"  - 正在创建数据库 '{self.app_db_name}'...")
                conn.execute(text(f'CREATE DATABASE "{self.app_db_name}"'))
            console.print("[bold green]✅ 数据库重建成功。[/bold green]")
            self.run_migrations()
        except Exception as e:
            console.print(f"[bold red]❌ 重建失败: {e}[/bold red]")
        finally:
            engine.dispose()

    def clear_database(self) -> None:
        """[危险] 清空数据库中的所有数据。"""
        if self.is_prod:
            console.print(
                "[bold red]❌ 操作被阻止: 禁止在生产环境中清空数据。[/bold red]"
            )
            return

        console.print(Panel(f"清空数据库: {self.app_db_name}", border_style="red"))
        engine = self._create_sync_engine(self.sync_app_url)
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
                console.print("  - 正在清空所有表...")
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(
                        text(
                            f'TRUNCATE TABLE "{table.schema}"."{table.name}" RESTART IDENTITY CASCADE;'
                        )
                    )
            console.print("[bold green]✅ 数据库已清空。[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ 清空失败: {e}[/bold red]")
        finally:
            engine.dispose()

    def run_interactive_doctor(self) -> None:
        """启动交互式医生菜单。"""
        if questionary is None:
            console.print(
                "[bold red]错误: 'questionary' 未安装。请运行 'poetry install --with dev'。[/bold red]"
            )
            return

        while True:
            choice = questionary.select(
                "请选择一个数据库医生操作:",
                choices=[
                    "🩺 健康检查 (Check Status)",
                    "🚀 运行迁移 (Upgrade to Head)",
                    "🪪 标记版本 (Stamp Version)",  # [新增] 交互式菜单中加入 stamp
                    "💥 [危险] 重建数据库 (Rebuild Database)",
                    "🗑️ [危险] 清空数据 (Clear Data)",
                    "🚪 退出 (Exit)",
                ],
            ).ask()

            if choice is None or choice.endswith("退出 (Exit)"):
                break
            elif choice.startswith("🩺"):
                self.check_status()
            elif choice.startswith("🚀"):
                self.run_migrations()
            elif choice.startswith("🪪"):  # [新增] 交互式菜单中调用 stamp
                rev_to_stamp = questionary.text(
                    "请输入要标记的版本号 (通常是 'head'):", default="head"
                ).ask()
                if rev_to_stamp:
                    self.stamp_version(rev_to_stamp)
            elif choice.startswith("💥"):
                if questionary.confirm(
                    f"确定要永久删除并重建 '{self.app_db_name}' 吗?", default=False
                ).ask():
                    self.rebuild_database()
            elif choice.startswith("🗑️"):
                if questionary.confirm(
                    f"确定要清空 '{self.app_db_name}' 的所有数据吗?", default=False
                ).ask():
                    self.clear_database()
            console.print("\n")

    # --- 审查 (Inspect) 功能 ---
    def inspect_database(self) -> None:
        """以可读格式显示数据库中的核心内容。"""
        engine = self._create_sync_engine(self.sync_app_url)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            console.print(
                Panel(
                    f"🔍 正在检查数据库: [yellow]{self.sync_app_url.render_as_string(hide_password=True)}[/yellow]",
                    border_style="blue",
                )
            )
            content_items = (
                session.query(ThContent).order_by(ThContent.created_at).all()
            )
            if not content_items:
                console.print("[yellow]数据库中没有内容条目。[/yellow]")
                return
            for content in content_items:
                self._render_content_panel(session, content)

    def _render_content_panel(self, session, content: ThContent) -> None:
        """渲染单个内容条目及其所有关联信息。"""
        uida_table = Table(
            box=None,
            show_header=False,
            padding=(0, 1),
            title="[bold]UIDA & Source[/bold]",
        )
        uida_table.add_column(style="dim cyan", width=12)
        uida_table.add_column()
        uida_table.add_row("Project ID:", content.project_id)
        uida_table.add_row("Namespace:", content.namespace)
        uida_table.add_row(
            "Source:",
            Syntax(
                json.dumps(content.source_payload_json, indent=2, ensure_ascii=False),
                "json",
                theme="monokai",
            ),
        )
        # Assuming keys_json is available on content object, if not, would need to re-evaluate
        # For now, it's not explicitly mapped in schema, so omitting this line to be safe.
        # uida_table.add_row(
        #     "Keys:",
        #     Syntax(json.dumps(content.keys_json, indent=2, ensure_ascii=False), "json", theme="monokai"),
        # )

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
            self._render_head_panel(session, head)

    def _render_head_panel(self, session, head: ThTransHead) -> None:
        """渲染单个翻译头及其修订。"""
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

        console.print(
            Panel(
                rev_table,
                title=f"🗣️  [magenta]Head[/magenta]: {head.id[:8]} ([bold]{head.target_lang}[/bold] / {head.variant_key})",
                border_style="magenta",
                expand=False,
            )
        )
