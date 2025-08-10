# packages/server/tools/db_doctor.py
"""
一个用于诊断、管理和修复 Trans-Hub Server 数据库环境的交互式命令行工具。
(v10 - 最终完整 .env 加载版)
"""
import os
import sys
from pathlib import Path

# --- 路径设置 ---
try:
    src_path = Path(__file__).resolve().parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from trans_hub.infrastructure.db._schema import Base
except (ImportError, IndexError):
    print("错误: 无法导入项目模块。请确保在 'packages/server' 目录下运行此脚本。")
    sys.exit(1)

import questionary
import structlog
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from trans_hub.config import TransHubConfig
from trans_hub.observability.logging_config import setup_logging

logger = structlog.get_logger("db_doctor")


class DatabaseDoctor:
    """封装了所有数据库诊断和修复操作的类。"""

    def __init__(self, config: TransHubConfig, alembic_cfg_path: Path):
        self.config = config
        self.alembic_cfg_path = alembic_cfg_path
        try:
            original_url = make_url(config.database_url)
            self.app_db_name = original_url.database

            # 使用 .copy() 来创建URL变体，确保所有字段都被保留
            # 1. 创建用于同步操作的应用数据库 URL
            app_sync_url = original_url.copy()
            app_sync_url.drivername = "postgresql+psycopg2"
            self.app_db_url = str(app_sync_url)

            # 2. 创建用于连接 'postgres' 数据库的维护 URL
            maintenance_sync_url = app_sync_url.copy()
            maintenance_sync_url.database = "postgres"
            self.maintenance_db_url = str(maintenance_sync_url)

        except Exception as e:
            logger.error("无法解析或构建数据库URL", url=config.database_url, error=e, exc_info=True)
            sys.exit(1)

    def get_alembic_versions(self) -> tuple[str, str]:
        """获取数据库中的当前版本和代码中的最新版本。"""
        db_version: str
        try:
            engine = create_engine(self.app_db_url)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                db_version = result.scalar_one_or_none() or "空 (未迁移)"
        except (OperationalError, ProgrammingError):
            db_version = "不存在或无法访问"
        
        script = ScriptDirectory.from_config(AlembicConfig(str(self.alembic_cfg_path)))
        head_version = script.get_current_head() or "未知"
        return db_version, head_version

    def check_db_status(self) -> bool:
        """执行一系列检查来验证数据库环境。"""
        logger.info("开始数据库环境健康检查...")
        errors = 0
        
        try:
            engine = create_engine(self.maintenance_db_url)
            with engine.connect() as conn:
                url_to_log = self.maintenance_db_url.replace(self.config.database_url.split('@')[0].split(':')[-1], '***')
                logger.info("维护库连接: ✅ 成功", url=url_to_log)
                result = conn.execute(text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user;"))
                if result.scalar_one():
                    logger.info("创建数据库权限: ✅ 拥有", details="用户有 CREATEDB 权限，可以运行集成测试。")
                else:
                    logger.error("创建数据库权限: ❌ 缺失", details="请运行: ALTER USER your_user CREATEDB;")
                    errors += 1
        except Exception as e:
            url_to_log = self.maintenance_db_url.replace(self.config.database_url.split('@')[0].split(':')[-1], '***')
            logger.error("维护库连接: ❌ 失败", url=url_to_log, error=str(e))
            errors += 1

        db_version, head_version = self.get_alembic_versions()
        if "无法访问" in db_version:
            logger.error("应用数据库: ❌ 不存在", database=self.app_db_name)
            errors += 1
        else:
            logger.info("应用数据库: ✅ 存在", database=self.app_db_name)
            if db_version == head_version:
                logger.info("Schema 版本: ✅ 最新", version=head_version)
            else:
                logger.warning("Schema 版本: ⚠️ 过期", db_version=db_version, code_version=head_version)
                errors += 1
        
        return errors == 0

    def rebuild_database(self) -> None:
        """(危险) 删除并重新创建应用数据库。"""
        if not questionary.confirm(f"您确定要重建数据库 '{self.app_db_name}' 吗? 这会删除所有数据。", default=False).ask():
            logger.warning("操作已取消。")
            return

        with structlog.contextvars.bound_contextvars(operation="rebuild_db"):
            try:
                engine = create_engine(self.maintenance_db_url, isolation_level="AUTOCOMMIT")
                with engine.connect() as conn:
                    logger.info(f"正在删除旧数据库 '{self.app_db_name}'...")
                    conn.execute(text(f'DROP DATABASE IF EXISTS "{self.app_db_name}" WITH (FORCE)'))
                    logger.info(f"正在创建新数据库 '{self.app_db_name}'...")
                    conn.execute(text(f'CREATE DATABASE "{self.app_db_name}"'))
                
                logger.info("正在运行数据库迁移...")
                alembic_cfg = AlembicConfig(str(self.alembic_cfg_path))
                alembic_cfg.set_main_option("sqlalchemy.url", self.app_db_url)
                command.upgrade(alembic_cfg, "head")
                logger.info("✅ 数据库已成功重建！", database=self.app_db_name)
            except Exception as e:
                logger.error("重建数据库失败", error=e, exc_info=True)

    def clear_database(self) -> None:
        """(危险) 清空应用数据库中的所有数据。"""
        if not questionary.confirm(f"您确定要清空数据库 '{self.app_db_name}' 中的所有数据吗?", default=False).ask():
            logger.warning("操作已取消。")
            return
        
        with structlog.contextvars.bound_contextvars(operation="clear_db"):
            try:
                engine = create_engine(self.app_db_url)
                with engine.begin() as conn:
                    for table in reversed(Base.metadata.sorted_tables):
                        logger.info(f"正在清空表: {table.name}...")
                        conn.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE;'))
                logger.info("✅ 数据库所有数据已成功清空！", database=self.app_db_name)
            except Exception as e:
                logger.error("清空数据库失败", error=e, exc_info=True)

def main():
    """主交互循环。"""
    setup_logging(log_level="INFO", log_format="console")
    
    try:
        # --- [核心] 强制加载 .env 并打印诊断信息 ---
        env_path = Path.cwd() / ".env"
        if not env_path.is_file():
            logger.error("在当前目录找不到 '.env' 文件。", path=str(Path.cwd()))
            sys.exit(1)
        
        load_dotenv(dotenv_path=env_path, override=True)
        
        config = TransHubConfig()

        # 使用 Rich Panel 打印诊断信息
        console = Console()
        console.print(Panel(
            f"[bold]从 .env 加载的配置[/bold]\n\n"
            f"  - [dim].env 文件路径:[/dim] {env_path}\n"
            f"  - [dim]读取到的 TH_DATABASE_URL:[/dim] [yellow]{config.database_url}[/yellow]",
            title="[cyan]配置加载诊断[/cyan]", border_style="cyan"
        ))
        
        alembic_cfg_path = Path.cwd() / "alembic.ini" 
        if not alembic_cfg_path.is_file():
            logger.error("在当前目录找不到 'alembic.ini'。")
            sys.exit(1)
        
        doctor = DatabaseDoctor(config, alembic_cfg_path)
        
        logger.info("欢迎使用 Trans-Hub 数据库医生")
        
        while True:
            choice = questionary.select(
                "请选择一个操作:",
                choices=[
                    questionary.Choice("🩺 健康检查 (Check Status)", "check"),
                    questionary.Choice("🔄 重建数据库 (Rebuild Database)", "rebuild"),
                    questionary.Choice("🗑️ 清空数据 (Clear Data)", "clear"),
                    questionary.Separator(),
                    questionary.Choice("🚪 退出 (Exit)", "exit"),
                ],
            ).ask()

            if choice == "check":
                if doctor.check_db_status():
                    logger.info("✅ 环境健康！")
                else:
                    logger.error("❌ 环境存在问题。")
            elif choice == "rebuild":
                doctor.rebuild_database()
            elif choice == "clear":
                doctor.clear_database()
            elif choice is None or choice == "exit":
                logger.info("再见！")
                break
    
    except KeyboardInterrupt:
        logger.warning("操作被用户中断。")
    except Exception:
        logger.error("工具运行时发生未知错误。", exc_info=True)


if __name__ == "__main__":
    main()