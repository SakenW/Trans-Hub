# trans_hub/persistence/__init__.py
# [v1.1 - 修正 PG 驱动加载]
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
        # [PG-Focus] 暂时忽略 SQLite 逻辑
        raise ConfigurationError("SQLite is temporarily disabled.")

    elif db_url.startswith("postgresql"):
        try:
            from .postgres import PostgresPersistenceHandler
        except ImportError as e:
            raise ConfigurationError(
                "要使用 PostgreSQL, 请安装 'asyncpg' 驱动: "
                '"pip install "trans-hub[postgres]"'
            ) from e
        
        # [v1.1 核心修正] 必须使用包含 "+asyncpg" 的原始 db_url 来创建异步引擎。
        # 移除错误的 .replace() 调用。
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