# packages/server/src/trans_hub/infrastructure/db/engine.py
"""
异步引擎工厂（统一数据库加载处理实现）

本模块提供统一的数据库引擎创建功能，支持自动识别和配置不同的数据库驱动：
- PostgreSQL+asyncpg：使用QueuePool连接池，支持schema
- SQLite+aiosqlite：使用NullPool，不支持schema
- MySQL+aiomysql：使用QueuePool连接池，支持schema

此模块还负责根据数据库驱动类型动态设置MetaData的schema配置，
确保在SQLite中不使用schema，而在其他数据库中使用配置的schema。
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ...config import TransHubConfig
from .base import metadata
from .utils import create_database_config, get_database_info

logger = structlog.get_logger("trans_hub.db.engine")


def create_async_db_engine(cfg: TransHubConfig) -> AsyncEngine:
    """
    创建统一配置的异步数据库引擎
    
    这是统一数据库加载处理的核心函数，它会：
    1. 自动识别数据库驱动类型（postgresql+asyncpg、sqlite+aiosqlite、mysql+aiomysql）
    2. 根据驱动类型应用最优的连接池配置
    3. 动态设置MetaData的schema配置
    4. 创建并返回配置优化的AsyncEngine
    
    Args:
        cfg: Trans-Hub应用配置对象
        
    Returns:
        AsyncEngine: 配置优化的异步数据库引擎
        
    Raises:
        ValueError: 当数据库驱动不受支持时
    """
    # 1. 创建统一的数据库配置
    db_config = create_database_config(cfg)
    
    # 2. 根据驱动类型动态设置MetaData的schema
    #    - SQLite不支持schema，设置为None
    #    - PostgreSQL和MySQL使用配置中定义的schema
    #    所有ORM模型通过base.py中的Base类自动与这个metadata实例关联
    metadata.schema = db_config.schema
    
    # 3. 记录数据库配置信息（用于调试）
    db_info = get_database_info(db_config.url)
    logger.info(
        "创建数据库引擎",
        driver=db_config.driver.value,
        schema=db_config.schema,
        supports_schema=db_config.supports_schema,
        pool_class=db_config.pool_config.get("poolclass", "default").__name__ 
        if hasattr(db_config.pool_config.get("poolclass", "default"), "__name__") 
        else str(db_config.pool_config.get("poolclass", "default")),
        **{k: v for k, v in db_info.items() if k not in ["username", "error"]}
    )
    
    # 4. 创建并返回引擎
    engine = create_async_engine(db_config.url, **db_config.pool_config)
    
    logger.debug(
        "数据库引擎创建完成",
        driver=db_config.driver.value,
        engine_id=id(engine)
    )
    
    return engine
