# trans_hub/persistence/__init__.py
# [v2.4.1 Final] 恢复 SQLite 支持，使项目功能完整。
"""本模块作为持久化层的公共入口，导出核心组件。"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from trans_hub.config import TransHubConfig
from trans_hub.core.exceptions import ConfigurationError
from trans_hub.core.interfaces import PersistenceHandler


def create_persistence_handler(config: TransHubConfig) -> PersistenceHandler:
    """
    根据配置创建、配置并返回一个具体的持久化处理器实例。
    这是实例化持久化层的唯一入口。
    """
    db_url = config.database_url

    if "sqlite" in db_url:
        try:
            from .sqlite import SQLitePersistenceHandler
        except ImportError as e:
            raise ConfigurationError(
                "要使用 SQLite, 请安装 'aiosqlite' 驱动: \"pip install aiosqlite\""
            ) from e

        engine = create_async_engine(db_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        return SQLitePersistenceHandler(sessionmaker, db_path=config.db_path)

    elif db_url.startswith("postgresql"):
        try:
            from .postgres import PostgresPersistenceHandler
        except ImportError as e:
            raise ConfigurationError(
                "要使用 PostgreSQL, 请安装 'asyncpg' 驱动: "
                '"pip install "trans-hub[postgres]"'
            ) from e

        engine = create_async_engine(db_url, pool_size=20, max_overflow=10)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        return PostgresPersistenceHandler(sessionmaker, dsn=db_url)

    else:
        raise ConfigurationError(f"不支持的数据库类型或驱动: '{db_url}'")


# 默认的持久化处理器仍然可以是 SQLite
from .sqlite import SQLitePersistenceHandler as DefaultPersistenceHandler

__all__ = [
    "create_persistence_handler",
    "DefaultPersistenceHandler",
    "PersistenceHandler",
]
