# packages/server/src/trans_hub/infrastructure/db/_session.py
"""
负责创建和管理数据库连接（引擎）和会话。
"""
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from trans_hub.config import TransHubConfig
from trans_hub_core.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)

def create_db_engine(config: TransHubConfig) -> AsyncEngine:
    """
    根据配置创建 SQLAlchemy 异步引擎，并校验驱动。
    """
    url = config.database_url
    
    # [新增] 校验 URL 是否包含有效的异步驱动
    # 宪章 2.3 要求明确指定驱动
    if not any(driver in url for driver in ["+aiosqlite", "+asyncpg", "+aiomysql"]):
        logger.error("数据库URL缺少异步驱动", url=url)
        raise ConfigurationError(
            f"数据库连接URL '{url}' 缺少必要的异步驱动 "
            f"(例如: '+asyncpg', '+aiosqlite')。"
        )

    logger.debug("正在创建数据库引擎", db_url=url.split('@')[-1])
    return create_async_engine(
        url,
        pool_size=20,          # 生产环境建议值
        max_overflow=10,
        pool_recycle=3600,     # 每小时回收一次连接
        echo=False,            # 生产环境应设为 False
    )


def create_db_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    """
    根据引擎创建 SQLAlchemy 异步会话工厂。
    """
    logger.debug("正在创建数据库会话工厂")
    return async_sessionmaker(engine, expire_on_commit=False)