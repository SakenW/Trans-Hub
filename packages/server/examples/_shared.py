# packages/server/examples/_shared.py
"""
包含所有示例共享的辅助函数和上下文管理器。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import structlog
from rich.console import Console
from rich.logging import RichHandler

from trans_hub.application.coordinator import Coordinator
from trans_hub.config import TransHubConfig

# --- 日志配置 ---
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.render_to_log_kwargs,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
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
    它会自动处理数据库文件的创建、Alembic 迁移、清理和 Coordinator 的生命周期。
    """
    db_file = Path(__file__).parent / db_file_name
    if db_file.exists():
        db_file.unlink()

    database_url = f"sqlite+aiosqlite:///{db_file.resolve()}"
    base_config = {"database_url": database_url, "default_source_lang": "en"}
    final_config_data = {**base_config, **config_overrides}

    config = TransHubConfig(
        database={"url": database_url},
        default_source_lang="en",
        **final_config_data,
    )

    # --- 运行 Alembic 迁移 ---
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        project_root = Path(__file__).resolve().parent.parent
        alembic_cfg_path = project_root / "alembic.ini"
        if not alembic_cfg_path.is_file():
            alembic_cfg_path = (
                project_root.parent / "alembic.ini"
            )  # monorepo adjustment

        alembic_cfg = AlembicConfig(str(alembic_cfg_path))
        sync_db_url = config.database.url.replace("+aiosqlite", "")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic 迁移已应用到示例数据库。")
    except Exception as e:
        logger.error("示例数据库迁移失败", error=e, exc_info=True)
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
