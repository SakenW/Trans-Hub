# packages/server/src/trans_hub/management/config_utils.py
"""
配置相关的工具函数，包括数据库连接验证、密码脱敏和配置加载。
"""

from __future__ import annotations
from typing import Union, Literal

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.exc import OperationalError

logger = structlog.get_logger("trans_hub.config_utils")


def mask_db_url(url: Union[str, URL, None]) -> str:
    """
    安全地脱敏一个数据库连接 URL，将其密码替换为 '***'。

    Args:
        url: 一个 SQLAlchemy URL 对象或 DSN 字符串，可以为 None。

    Returns:
        一个脱敏后的 DSN 字符串，适合在日志或控制台中显示。
    """
    if url is None:
        return "[未配置]"
    
    try:
        url_obj = make_url(url)
        # 使用 render_as_string(hide_password=True) 是最健壮的方式
        return url_obj.render_as_string(hide_password=True)
    except Exception:
        # 如果 URL 格式不正确，返回一个安全的提示信息
        return "[无法解析的数据库 URL]"


def get_real_db_url(url: Union[str, URL]) -> str:
    """
    获取包含真实密码的数据库连接 URL 字符串。
    
    Args:
        url: 一个 SQLAlchemy URL 对象或 DSN 字符串。
        
    Returns:
        包含真实密码的 DSN 字符串，用于实际数据库连接。
        
    Note:
        此函数返回的字符串包含明文密码，仅应用于实际数据库连接，
        严禁用于日志记录或显示。
    """
    url_obj = make_url(url)
    return url_obj.render_as_string(hide_password=False)


def convert_async_to_sync_url(async_url: Union[str, URL]) -> str:
    """
    将异步数据库 URL 转换为同步版本，用于连接测试。
    
    Args:
        async_url: 异步数据库 URL。
        
    Returns:
        对应的同步数据库 URL 字符串。
    """
    url_obj = make_url(async_url)
    real_url = url_obj.render_as_string(hide_password=False)
    
    # 将异步驱动转换为同步驱动
    if "+asyncpg" in real_url:
        return real_url.replace("+asyncpg", "+psycopg")
    elif "+aiosqlite" in real_url:
        return real_url.replace("+aiosqlite", "")
    elif "+aiomysql" in real_url:
        return real_url.replace("+aiomysql", "+pymysql")
    else:
        return real_url


def validate_database_connection(database_url: Union[str, URL], 
                               maintenance_url: Union[str, URL, None] = None,
                               connection_type: str = "数据库") -> bool:
    """
    验证数据库连接是否可用。
    
    Args:
        database_url: 主数据库连接 URL。
        maintenance_url: 维护数据库连接 URL（可选）。
        connection_type: 连接类型描述，用于日志记录。
        
    Returns:
        如果所有连接都成功则返回 True，否则返回 False。
    """
    try:
        # 测试维护数据库连接
        if maintenance_url:
            maint_real_url = get_real_db_url(maintenance_url)
            maint_engine = create_engine(maint_real_url)
            with maint_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            maint_engine.dispose()
            logger.debug(f"{connection_type}维护数据库连接验证成功")
        
        # 测试主数据库连接（转换为同步版本进行测试）
        sync_url = convert_async_to_sync_url(database_url)
        test_engine = create_engine(sync_url)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        logger.debug(f"{connection_type}主数据库连接验证成功")
        
        return True
    except OperationalError as e:
        logger.error(
            f"{connection_type}连接验证失败",
            error=str(e),
            main_db_url=mask_db_url(database_url),
            maint_db_url=mask_db_url(maintenance_url) if maintenance_url else None
        )
        return False
    except Exception as e:
        logger.error(
            f"{connection_type}连接验证时发生意外错误",
            error=str(e),
            error_type=type(e).__name__
        )
        return False
