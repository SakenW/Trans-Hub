# packages/server/tools/db_doctor.py
"""
数据库诊断/修复工具（v28）
- 启动先选环境 test/prod（默认 test）
- 统一调用 config_loader.load_config_from_env(mode=..., strict=True)
- Alembic 迁移（psycopg2），失败兜底（ORM 建表 + 手动写入 alembic_version）
- 生产保护：禁止重建/清空
"""

import os
import sys
import argparse
from pathlib import Path

# 确保能导入 packages/server/src
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import questionary
import structlog
from sqlalchemy import create_engine, text, URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

from trans_hub.infrastructure.db._schema import Base
from trans_hub.config import TransHubConfig
from trans_hub.config_loader import load_config_from_env
from trans_hub.observability.logging_config import setup_logging

logger = structlog.get_logger("db_doctor_final")


def _server_root() -> Path:
    """packages/server"""
    return Path(__file__).resolve().parents[1]


def _masked(url: URL | str) -> str:
    """日志脱敏，不影响真实连接"""
    try:
        return make_url(str(url)).render_as_string(hide_password=True)
    except Exception:
        return str(url)


def _print_sep(title: str | None = None) -> None:
    bar = "=" * 96
    if title:
        print(f"\n{bar}\n{title}\n{bar}\n")
    else:
        print(f"\n{bar}\n")


def _pause_return() -> None:
    try:
        input("按回车键返回菜单...")
    except EOFError:
        pass


def _build_alembic_config(alembic_ini: Path, sqlalchemy_url: URL) -> AlembicConfig:
    cfg = AlembicConfig(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", str(sqlalchemy_url))
    sl = cfg.get_main_option("script_location")
    if sl:
        sl_path = Path(sl)
        if not sl_path.is_absolute():
            sl_path = (alembic_ini.parent / sl_path).resolve()
        cfg.set_main_option("script_location", str(sl_path))
        print(f"[BOOT] 使用迁移脚本目录: {sl_path}")
    else:
        print("[BOOT][WARN] alembic.ini 未配置 script_location，Alembic 将无法找到迁移脚本")
    return cfg


class DatabaseDoctor:
    def __init__(self, config: TransHubConfig, alembic_cfg_path: Path):
        self.alembic_cfg_path = alembic_cfg_path
        try:
            app_url_obj = make_url(config.database_url)
            maint_url_str = config.maintenance_database_url or str(app_url_obj.set(database="postgres"))
            maint_url_obj = make_url(maint_url_str)

            self.app_db_name = app_url_obj.database
            self.app_db_url = URL.create(
                drivername="postgresql+psycopg2",
                username=app_url_obj.username,
                password=app_url_obj.password,
                host=app_url_obj.host,
                port=app_url_obj.port,
                database=self.app_db_name,
            )
            self.maintenance_db_url = URL.create(
                drivername="postgresql+psycopg2",
                username=maint_url_obj.username,
                password=maint_url_obj.password,
                host=maint_url_obj.host,
                port=maint_url_obj.port,
                database=maint_url_obj.database or "postgres",
            )
        except Exception as e:
            logger.error("无法解析数据库URL", error=e, exc_info=True)
            print(f"[FATAL] 无法解析数据库URL: {e!r}")
            sys.exit(1)

    def get_alembic_versions(self) -> tuple[str, str]:
        print(f"[CHECK] 连接应用数据库: {_masked(self.app_db_url)}")
        db_version: str
        try:
            engine = create_engine(self.app_db_url)
            with engine.connect() as conn:
                print("[CHECK] 应用数据库连接成功")
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                val = result.scalar_one_or_none()
                db_version = str(val) if val else "空 (未迁移)"
                print(f"[CHECK] 当前 alembic_version: {db_version}")
        except ProgrammingError as e:
            if 'relation "alembic_version" does not exist' in str(e):
                print("[CHECK][WARN] 未发现 alembic_version 表，视为未迁移")
                db_version = "空 (未迁移)"
            else:
                logger.error("查询 Alembic 版本失败", error=str(e))
                print(f"[CHECK][ERR] 查询 Alembic 版本失败: {e!r}")
                db_version = "未知（查询失败）"
        except OperationalError as e:
            logger.error("无法连接或查询应用数据库", error=str(e))
            print(f"[CHECK][ERR] 无法连接或查询应用数据库: {e!r}")
            db_version = "无法访问"

        cfg = _build_alembic_config(self.alembic_cfg_path, self.app_db_url)
        try:
            head_version = ScriptDirectory.from_config(cfg).get_current_head() or "未知"
        except Exception as e:
            print(f"[CHECK][ERR] 读取 Alembic head 失败: {e!r}")
            head_version = "未知"

        return db_version, head_version

    def check_db_status(self) -> bool:
        print("[CHECK] 开始数据库环境健康检查 ...")
        errors = 0
        print(f"[CHECK] 连接维护库: {_masked(self.maintenance_db_url)}")
        try:
            engine = create_engine(self.maintenance_db_url)
            with engine.connect() as conn:
                print("[CHECK] 维护库连接成功")
                result = conn.execute(text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user;"))
                if result.scalar_one():
                    print("[CHECK] 当前用户拥有 CREATEDB 权限")
                else:
                    print("[CHECK][ERR] 当前用户缺少 CREATEDB 权限")
                    errors += 1
        except Exception as e:
            print(f"[CHECK][ERR] 维护库连接失败: {e!r}")
            errors += 1
            return False

        db_version, head_version = self.get_alembic_versions()
        print(f"[CHECK] 对比版本: db={db_version} head={head_version}")

        if db_version in ("无法访问", "未知（查询失败）"):
            errors += 1
        elif db_version == "空 (未迁移)":
            print("[CHECK][WARN] 数据库未迁移，建议执行 '运行迁移(Upgrade to Head)'。")
            errors += 1
        elif db_version != head_version:
            print("[CHECK][WARN] 版本不一致，建议执行迁移。")
            errors += 1

        healthy = errors == 0
        print(f"[CHECK] 结论: {'健康' if healthy else '存在问题'}")
        return healthy

    def run_migrations(self) -> None:
        print("[MIGRATE] 开始运行迁移流程 ...")
        cfg = _build_alembic_config(self.alembic_cfg_path, self.app_db_url)
        head = None
        try:
            script = ScriptDirectory.from_config(cfg)
            head = script.get_current_head()
            print(f"[MIGRATE] 检测到 Alembic head = {head}")
            print("[MIGRATE] 执行 alembic upgrade head ...")
            command.upgrade(cfg, "head")
            print("[MIGRATE][OK] upgrade head 完成")
            return
        except Exception as e:
            logger.error("upgrade head 失败，启用强力兜底...", error=str(e))
            print(f"[MIGRATE][ERR] upgrade head 失败: {e!r}")
            self._fallback_migration(head)

    def _fallback_migration(self, head: str | None) -> None:
        print("[MIGRATE][FALLBACK] 启用强力兜底：ORM 建表 + 手工写入 alembic_version")
        try:
            engine = create_engine(self.app_db_url)
            with engine.begin() as conn:
                Base.metadata.create_all(bind=conn)
                print("[MIGRATE][FALLBACK] 已执行 Base.metadata.create_all()")
                if head:
                    conn.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)'))
                    conn.execute(text('TRUNCATE alembic_version'))
                    conn.execute(text('INSERT INTO alembic_version(version_num) VALUES (:v)'), {"v": head})
                    print(f"[MIGRATE][FALLBACK] 已写入 alembic_version = {head}")
        except Exception as e:
            logger.error("兜底迁移失败", error=e, exc_info=True)
            print(f"[MIGRATE][FATAL] 兜底迁移失败: {e!r}")
        else:
            print("[MIGRATE][OK] 兜底迁移完成")

    def rebuild_database(self) -> None:
        if os.getenv("TH_ENV") == "production":
            logger.error("生产环境禁止重建数据库。")
            print("[REBUILD][BLOCK] TH_ENV=production，禁止重建数据库")
            return
        try:
            engine = create_engine(self.maintenance_db_url, isolation_level="AUTOCOMMIT")
            with engine.connect() as conn:
                print(f"[REBUILD] 删除数据库: {self.app_db_name}")
                conn.execute(text(f'DROP DATABASE IF EXISTS "{self.app_db_name}" WITH (FORCE)'))
                print(f"[REBUILD] 创建数据库: {self.app_db_name}")
                conn.execute(text(f'CREATE DATABASE "{self.app_db_name}"'))
            print("[REBUILD] 重建完成，准备运行迁移 ...")
            self.run_migrations()
            print("[REBUILD][OK] 数据库已成功重建并迁移完成")
        except Exception as e:
            logger.error("重建数据库失败", error=e, exc_info=True)
            print(f"[REBUILD][ERR] 重建数据库失败: {e!r}")

    def clear_database(self) -> None:
        if os.getenv("TH_ENV") == "production":
            logger.error("生产环境禁止清空数据库。")
            print("[CLEAR][BLOCK] TH_ENV=production，禁止清空数据库")
            return
        try:
            engine = create_engine(str(self.app_db_url))
            with engine.begin() as conn:
                for table in reversed(Base.metadata.sorted_tables):
                    print(f"[CLEAR] 清空表: {table.name}")
                    conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE;'))
            print("[CLEAR][OK] 已清空数据库所有数据")
        except Exception as e:
            logger.error("清空数据库失败", error=e, exc_info=True)
            print(f"[CLEAR][ERR] 清空数据库失败: {e!r}")


def _select_env_if_needed(arg_env: str | None) -> str:
    if arg_env:
        return arg_env
    choice = questionary.select(
        "请选择运行环境（默认测试环境）:",
        choices=[
            questionary.Choice("🧪 测试环境（.env.test）", "test"),
            questionary.Choice("🏭 正式环境（.env）", "prod"),
        ],
        default="test",
    ).unsafe_ask()
    return choice or "test"


def run_interactive(doctor: DatabaseDoctor) -> None:
    print("[BOOT] 进入交互模式")
    while True:
        choice = questionary.select(
            "请选择一个操作:",
            choices=[
                questionary.Choice("🩺 健康检查 (Check Status)", "check"),
                questionary.Choice("🚀 运行迁移 (Upgrade to Head)", "upgrade"),
                questionary.Choice("🔄 重建数据库 (Rebuild Database)", "rebuild"),
                questionary.Choice("🗑️ 清空数据 (Clear Data)", "clear"),
                questionary.Separator(),
                questionary.Choice("🚪 退出 (Exit)", "exit"),
            ],
        ).unsafe_ask()

        if choice is None or choice == "exit":
            print("[BOOT] 退出交互模式")
            break

        if choice == "check":
            _print_sep("开始：健康检查")
            ok = doctor.check_db_status()
            print(f"[RESULT] {'✅ 环境健康' if ok else '❌ 环境存在问题'}")
            _print_sep("结束：健康检查")
            _pause_return()
        elif choice == "upgrade":
            _print_sep("开始：运行迁移 (Upgrade to Head)")
            doctor.run_migrations()
            _print_sep("结束：运行迁移")
            _pause_return()
        elif choice == "rebuild":
            confirm = questionary.confirm(
                f"您确定要重建数据库 '{doctor.app_db_name}' 吗? 这会删除所有数据。", default=False
            ).unsafe_ask()
            if confirm:
                _print_sep("开始：重建数据库")
                doctor.rebuild_database()
                _print_sep("结束：重建数据库")
                _pause_return()
        elif choice == "clear":
            confirm = questionary.confirm(
                f"您确定要清空数据库 '{doctor.app_db_name}' 中的所有数据吗?", default=False
            ).unsafe_ask()
            if confirm:
                _print_sep("开始：清空数据")
                doctor.clear_database()
                _print_sep("结束：清空数据")
                _pause_return()


def run_cli(args: argparse.Namespace, doctor: DatabaseDoctor) -> int:
    rc = 0
    if args.check:
        _print_sep("开始：健康检查")
        ok = doctor.check_db_status()
        print(f"[RESULT] {'✅ 环境健康' if ok else '❌ 环境存在问题'}")
        _print_sep("结束：健康检查")
        if not ok:
            rc = 2
    if args.upgrade:
        _print_sep("开始：运行迁移 (Upgrade to Head)")
        doctor.run_migrations()
        _print_sep("结束：运行迁移")
    if args.rebuild:
        _print_sep("开始：重建数据库")
        doctor.rebuild_database()
        _print_sep("结束：重建数据库")
    if args.clear:
        _print_sep("开始：清空数据")
        doctor.clear_database()
        _print_sep("结束：清空数据")
    return rc


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trans-Hub 数据库医生（交互/非交互）")
    g = p.add_argument_group("非交互动作（任选其一或多个）")
    g.add_argument("--check", action="store_true", help="执行健康检查")
    g.add_argument("--upgrade", action="store_true", help="运行 Alembic 迁移至 head")
    g.add_argument("--rebuild", action="store_true", help="删除并重建数据库（危险）")
    g.add_argument("--clear", action="store_true", help="清空所有表数据（危险）")
    p.add_argument("--env", choices=["test", "prod"], default="test", help="运行环境（默认 test）")
    p.add_argument("--yes", action="store_true", help="（占位，当前未强制）")
    return p.parse_args(argv)


def main():
    setup_logging(log_level="INFO", log_format="console")
    try:
        args = parse_args(sys.argv[1:])
        env_mode = _select_env_if_needed(args.env)

        # 使用统一加载器（严格模式）加载对应环境配置
        config = load_config_from_env(mode=env_mode, strict=True)

        alembic_cfg_path = Path(os.getenv("TH_ALEMBIC_INI_PATH", _server_root() / "alembic.ini"))

        # 展示配置（用于诊断）
        try:
            from rich.console import Console
            from rich.panel import Panel
            Console().print(
                Panel(
                    f"[bold]从环境加载的配置[/bold]\n\n"
                    f"  - [dim]TH_DATABASE_URL:[/dim] [yellow]{config.database_url}[/yellow]\n"
                    f"  - [dim]TH_MAINTENANCE_DATABASE_URL:[/dim] [yellow]{config.maintenance_database_url}[/yellow]\n"
                    f"  - [dim]Alembic INI 路径:[/dim] [yellow]{alembic_cfg_path}[/yellow]",
                    title="[cyan]配置加载诊断[/cyan]", border_style="cyan"
                )
            )
        except Exception:
            pass

        doctor = DatabaseDoctor(config, alembic_cfg_path)

        if not (args.check or args.upgrade or args.rebuild or args.clear):
            run_interactive(doctor)
        else:
            sys.exit(run_cli(args, doctor))

    except (FileNotFoundError, ValueError) as e:
        logger.error("启动失败", error=str(e))
        print(f"[FATAL] 启动失败: {e!r}")
        sys.exit(1)
    except Exception as e:
        logger.error("工具运行时发生未知错误。", exc_info=True)
        print(f"[FATAL] 工具运行时发生未知错误: {e!r}")
        sys.exit(99)


if __name__ == "__main__":
    main()