# packages/server/src/trans_hub/infrastructure/db/_session.py
"""
负责创建和管理数据库连接（引擎）和会话。
"""
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from trans_hub.config import TransHubConfig


def create_db_engine(config: TransHubConfig) -> AsyncEngine:
    """
    根据配置创建 SQLAlchemy 异步引擎。
    """
    return create_async_engine(
        config.database_url,
        pool_size=20,          # 生产环境建议值
        max_overflow=10,
        pool_recycle=3600,     # 每小时回收一次连接
        echo=False,            # 生产环境应设为 False
    )


def create_db_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    """
    根据引擎创建 SQLAlchemy 异步会话工厂。
    """
    return async_sessionmaker(engine, expire_on_commit=False)