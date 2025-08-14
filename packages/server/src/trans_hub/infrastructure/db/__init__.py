# packages/server/src/trans_hub/infrastructure/db/__init__.py
"""
数据库公共 API（唯一对外入口，遵守技术宪章）

使用约定：
- 仅从本包导入公共函数，不直接引用内部模块路径。
- 不提供历史兼容别名；一切以最优化命名为准。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from .engine import create_async_db_engine
from .session import create_async_sessionmaker, session_scope


async def dispose_engine(engine: AsyncEngine) -> None:
    """
    释放底层连接池资源（异步等待）。
    注意：
    - SQLAlchemy 2.x 中 AsyncEngine.dispose() 为 awaitable；
    - 在测试/进程退出时由上层显式 await 调用。
    """
    await engine.dispose()


__all__ = [
    "create_async_db_engine",
    "create_async_sessionmaker",
    "session_scope",
    "dispose_engine",
]
