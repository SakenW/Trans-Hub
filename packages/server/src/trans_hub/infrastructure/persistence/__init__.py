# packages/server/src/trans_hub/infrastructure/persistence/__init__.py
"""
持久化处理器的工厂模块。

根据配置动态选择并创建具体的 `PersistenceHandler` 实现，
这是解耦应用层与具体数据库实现的关键。
"""

from __future__ import annotations

from sqlalchemy.engine.url import make_url

from trans_hub.config import TransHubConfig
from trans_hub_core.exceptions import ConfigurationError
from trans_hub_core.interfaces import PersistenceHandler

from ._postgres import PostgresPersistenceHandler
from ._sqlite import SQLitePersistenceHandler


def create_persistence_handler(
    config: TransHubConfig, sessionmaker
) -> PersistenceHandler:
    """根据配置创建、配置并返回一个具体的持久化处理器实例。"""
    db_url = config.database_url
    url = make_url(db_url)

    if url.drivername.startswith("sqlite"):
        return SQLitePersistenceHandler(sessionmaker)
    if url.drivername.startswith("postgresql"):
        return PostgresPersistenceHandler(sessionmaker, str(db_url))

    raise ConfigurationError(f"不支持的数据库驱动: {url.drivername}")
