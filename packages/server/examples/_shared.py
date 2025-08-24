# packages/server/examples/_shared.py
"""
包含所有示例共享的辅助函数和上下文管理器。
[v3.0.0 重构版]
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from rich.console import Console
from rich.logging import RichHandler

from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config
from trans_hub.management.db_service import DbService
from trans_hub.management.utils import find_alembic_ini  # [修改] 从共享模块导入

# --- 日志配置 (保持不变) ---
# ... (structlog 配置保持不变) ...
handler = RichHandler(rich_tracebacks=True, console=Console(stderr=True))
logger = structlog.get_logger("trans_hub_example")
logger.setLevel("INFO")
logger.addHandler(handler)


@asynccontextmanager
async def example_runner(
    db_file_name: str, **config_overrides: Any
) -> AsyncGenerator[Coordinator, None]:
    """
    一个异步上下文管理器，负责准备和清理示例的运行环境。
    它现在使用标准的 bootstrap 和 DbService 来确保环境与生产一致。
    """
    db_file = Path(__file__).parent / db_file_name
    if db_file.exists():
        db_file.unlink()

    # 1. 使用标准引导程序加载配置，并允许覆盖
    # 注意：示例使用 "prod" 模式，因为它不应该依赖测试环境配置
    # 我们通过 os.environ 注入覆盖，模拟真实部署场景
    database_url = f"sqlite+aiosqlite:///{db_file.resolve()}"
    os.environ["TRANSHUB_DATABASE__URL"] = database_url
    for key, value in config_overrides.items():
        # 模拟环境变量的格式
        env_key = f"TRANSHUB_{key.upper()}"
        os.environ[env_key] = str(value)

    config = create_app_config(env_mode="prod")

    # 2. 使用生产级的 DbService 来运行迁移
    try:
        # 对于 SQLite，维护 DSN 就是同步 DSN
        sync_db_url = config.database.url.replace("+aiosqlite", "")
        # 临时设置维护URL，以便DbService工作
        config.maintenance_database_url = sync_db_url

        service = DbService(config, str(find_alembic_ini()))  # [修改] 使用导入的函数
        service.run_migrations()
        logger.info("Alembic 迁移已应用到示例数据库。")
    except Exception as e:
        logger.error("示例数据库迁移失败", error=e, exc_info=True)
        # 清理环境变量
        del os.environ["TRANSHUB_DATABASE__URL"]
        raise

    coordinator = Coordinator(config=config)

    try:
        await coordinator.initialize()
        logger.info("✅ 示例环境已就绪", db_path=str(db_file))
        yield coordinator
    finally:
        await coordinator.close()
        logger.info("🚪 协调器已关闭")
        if db_file.exists():
            db_file.unlink()
            logger.info("🧹 临时数据库文件已清理")
        # 清理注入的环境变量
        del os.environ["TRANSHUB_DATABASE__URL"]
        for key in config_overrides:
            env_key = f"TRANSHUB_{key.upper()}"
            if env_key in os.environ:
                del os.environ[env_key]
