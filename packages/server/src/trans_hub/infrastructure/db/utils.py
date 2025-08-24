# packages/server/src/trans_hub/infrastructure/db/utils.py
"""
数据库工具模块：统一的数据库驱动识别和配置处理

本模块提供了统一的数据库加载处理机制，能够自动识别不同的数据库驱动类型
（postgresql+asyncpg、sqlite+aiosqlite、mysql+aiomysql）并应用相应的优化配置。

主要功能：
- 自动识别数据库驱动类型
- 根据驱动类型应用最优的连接池配置
- 处理不同数据库的schema配置差异
- 提供统一的数据库连接参数生成接口
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool, QueuePool

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig


class DatabaseDriver(Enum):
    """支持的数据库驱动类型枚举"""
    SQLITE = "sqlite+aiosqlite"
    POSTGRESQL = "postgresql+asyncpg"
    MYSQL = "mysql+aiomysql"


class DatabaseConfig:
    """数据库配置信息容器"""
    
    def __init__(
        self,
        driver: DatabaseDriver,
        url: str,
        schema: str | None = None,
        pool_config: dict[str, Any] | None = None
    ):
        self.driver = driver
        self.url = url
        self.schema = schema
        self.pool_config = pool_config or {}
    
    @property
    def is_sqlite(self) -> bool:
        """判断是否为SQLite数据库"""
        return self.driver == DatabaseDriver.SQLITE
    
    @property
    def is_postgresql(self) -> bool:
        """判断是否为PostgreSQL数据库"""
        return self.driver == DatabaseDriver.POSTGRESQL
    
    @property
    def is_mysql(self) -> bool:
        """判断是否为MySQL数据库"""
        return self.driver == DatabaseDriver.MYSQL
    
    @property
    def supports_schema(self) -> bool:
        """判断数据库是否支持schema"""
        return not self.is_sqlite


def detect_database_driver(database_url: str) -> DatabaseDriver:
    """
    自动检测数据库驱动类型
    
    Args:
        database_url: 数据库连接URL
        
    Returns:
        DatabaseDriver: 检测到的驱动类型
        
    Raises:
        ValueError: 当驱动类型不受支持时
    """
    try:
        url = make_url(database_url)
        drivername = url.drivername.lower()
        
        # 映射驱动名称到枚举
        driver_mapping = {
            "sqlite+aiosqlite": DatabaseDriver.SQLITE,
            "postgresql+asyncpg": DatabaseDriver.POSTGRESQL,
            "mysql+aiomysql": DatabaseDriver.MYSQL,
        }
        
        if drivername in driver_mapping:
            return driver_mapping[drivername]
        
        # 处理简化的驱动名称
        if drivername.startswith("sqlite"):
            return DatabaseDriver.SQLITE
        elif drivername.startswith("postgresql"):
            return DatabaseDriver.POSTGRESQL
        elif drivername.startswith("mysql"):
            return DatabaseDriver.MYSQL
        
        raise ValueError(
            f"不支持的数据库驱动：{drivername}。"
            f"支持的驱动：{', '.join([d.value for d in DatabaseDriver])}"
        )
        
    except Exception as e:
        raise ValueError(f"无法解析数据库URL '{database_url}'：{e}") from e


def create_optimal_pool_config(
    driver: DatabaseDriver,
    config: "TransHubConfig"
) -> dict[str, Any]:
    """
    根据数据库驱动类型创建最优的连接池配置
    
    Args:
        driver: 数据库驱动类型
        config: 应用配置对象
        
    Returns:
        dict: 连接池配置参数
    """
    pool_config: dict[str, Any] = {
        "echo": config.db_echo or getattr(config.database, "echo", False),
        "pool_pre_ping": config.db_pool_pre_ping,
        "future": True,
    }
    
    if driver == DatabaseDriver.SQLITE:
        # SQLite 使用 NullPool，避免多进程/多线程下的共享句柄问题
        pool_config["poolclass"] = NullPool
    else:
        # PostgreSQL 和 MySQL 使用连接池
        pool_config["poolclass"] = QueuePool
        
        # 应用连接池参数
        if config.db_pool_size is not None:
            pool_config["pool_size"] = config.db_pool_size
        if config.db_max_overflow is not None:
            pool_config["max_overflow"] = config.db_max_overflow
        if config.db_pool_recycle is not None:
            pool_config["pool_recycle"] = config.db_pool_recycle
        
        pool_config["pool_timeout"] = config.db_pool_timeout
        
        # 针对不同数据库的特定优化
        if driver == DatabaseDriver.POSTGRESQL:
            # PostgreSQL 特定优化
            pool_config.setdefault("pool_size", 10)
            pool_config.setdefault("max_overflow", 20)
        elif driver == DatabaseDriver.MYSQL:
            # MySQL 特定优化
            pool_config.setdefault("pool_size", 8)
            pool_config.setdefault("max_overflow", 15)
    
    return pool_config


def resolve_database_schema(
    driver: DatabaseDriver,
    config: "TransHubConfig"
) -> str | None:
    """
    根据数据库驱动类型解析schema配置
    
    Args:
        driver: 数据库驱动类型
        config: 应用配置对象
        
    Returns:
        str | None: schema名称，SQLite返回None
    """
    # 获取默认schema配置
    default_schema: str | None = getattr(config.database, "default_schema", None)
    
    # 根据驱动类型处理schema
    if driver == DatabaseDriver.SQLITE:
        return None  # SQLite不支持schema
    
    return default_schema


def create_database_config(config: "TransHubConfig") -> DatabaseConfig:
    """
    创建统一的数据库配置对象
    
    这是统一数据库加载处理的核心入口函数，它会：
    1. 自动检测数据库驱动类型
    2. 生成最优的连接池配置
    3. 解析schema配置
    4. 返回完整的数据库配置对象
    
    Args:
        config: 应用配置对象
        
    Returns:
        DatabaseConfig: 统一的数据库配置对象
    """
    database_url = config.database.url
    
    # 1. 自动检测驱动类型
    driver = detect_database_driver(database_url)
    
    # 2. 创建最优连接池配置
    pool_config = create_optimal_pool_config(driver, config)
    
    # 3. 解析schema配置
    schema = resolve_database_schema(driver, config)
    
    return DatabaseConfig(
        driver=driver,
        url=database_url,
        schema=schema,
        pool_config=pool_config
    )


def get_database_info(database_url: str) -> dict[str, Any]:
    """
    获取数据库连接的详细信息（用于调试和日志）
    
    Args:
        database_url: 数据库连接URL
        
    Returns:
        dict: 包含数据库信息的字典
    """
    try:
        url = make_url(database_url)
        driver = detect_database_driver(database_url)
        
        return {
            "driver": driver.value,
            "host": url.host,
            "port": url.port,
            "database": url.database,
            "username": url.username,
            "supports_schema": driver != DatabaseDriver.SQLITE,
            "is_sqlite": driver == DatabaseDriver.SQLITE,
            "is_postgresql": driver == DatabaseDriver.POSTGRESQL,
            "is_mysql": driver == DatabaseDriver.MYSQL,
        }
    except Exception as e:
        return {
            "error": str(e),
            "raw_url": database_url
        }