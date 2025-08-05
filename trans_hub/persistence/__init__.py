# trans_hub/persistence/__init__.py
"""本模块作为持久化层的公共入口，导出核心组件。"""

from trans_hub.config import TransHubConfig
from trans_hub.core.exceptions import ConfigurationError
from trans_hub.core.interfaces import PersistenceHandler


# v4.0 规划：根据 URL scheme 动态选择持久化处理器
def create_persistence_handler(config: TransHubConfig) -> PersistenceHandler:
    """根据配置创建并返回一个具体的持久化处理器实例。"""
    db_url = config.database_url

    if db_url.startswith("sqlite"):
        from .sqlite import SQLitePersistenceHandler

        return SQLitePersistenceHandler(db_path=config.db_path)
    elif db_url.startswith("postgresql") or db_url.startswith("postgres"):
        try:
            from .postgres import PostgresPersistenceHandler

            return PostgresPersistenceHandler(dsn=db_url)
        except ImportError as e:
            raise ConfigurationError(
                "要使用 PostgreSQL, 请安装 'asyncpg' 驱动: "
                '"pip install "trans-hub[postgres]"'
            ) from e
    else:
        raise ConfigurationError(f"不支持的数据库类型或驱动: '{db_url}'")


# 为了向后兼容和类型提示，仍然导出默认的 SQLite 实现
from .sqlite import SQLitePersistenceHandler as DefaultPersistenceHandler

__all__ = [
    "create_persistence_handler",
    "DefaultPersistenceHandler",
    "PersistenceHandler",
]
