# trans_hub/persistence/__init__.py
"""本模块作为持久化层的公共入口，导出核心组件。"""

from trans_hub.config import TransHubConfig
from trans_hub.exceptions import ConfigurationError
from trans_hub.interfaces import PersistenceHandler

from .sqlite import SQLitePersistenceHandler as DefaultPersistenceHandler

__all__ = [
    "create_persistence_handler",
    "DefaultPersistenceHandler",
    "PersistenceHandler",
]


def create_persistence_handler(config: TransHubConfig) -> PersistenceHandler:
    """根据配置创建并返回一个具体的持久化处理器实例。"""
    db_url = config.database_url
    if db_url.startswith("sqlite"):
        return DefaultPersistenceHandler(db_path=config.db_path)
    else:
        raise ConfigurationError(f"不支持的数据库类型或驱动: '{db_url}'")
