# packages/server/src/trans_hub/infrastructure/persistence/__init__.py
"""
持久化处理器的工厂模块。

根据配置动态选择并创建具体的 `PersistenceHandler` 实现，
这是解耦应用层与具体数据库实现的关键。
"""
from trans_hub.config import TransHubConfig
from trans_hub_core.exceptions import ConfigurationError
from trans_hub_core.interfaces import PersistenceHandler

from ._postgres import PostgresPersistenceHandler
from ._sqlite import SQLitePersistenceHandler


def create_persistence_handler(
    config: TransHubConfig, sessionmaker
) -> PersistenceHandler:
    """
    根据配置创建、配置并返回一个具体的持久化处理器实例。
    这是实例化持久化层的唯一入口。
    """
    db_url = config.database_url

    if "sqlite" in db_url:
        return SQLitePersistenceHandler(sessionmaker)
    elif db_url.startswith("postgresql"):
        return PostgresPersistenceHandler(sessionmaker, dsn=db_url)
    # elif db_url.startswith("mysql"):
    #     # 未来可以添加 MySQL 实现
    #     from ._mysql import MySQLPersistenceHandler
    #     return MySQLPersistenceHandler(sessionmaker)
    else:
        raise ConfigurationError(f"不支持的数据库类型或驱动: '{db_url}'")