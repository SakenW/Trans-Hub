# packages/server/src/trans_hub/infrastructure/db/session.py
"""
会话工厂与事务作用域（最优化实现，遵守技术宪章）

- create_async_sessionmaker(engine)：标准化创建 AsyncSession 工厂
- session_scope(sessionmaker)：统一事务域（自动提交/回滚/关闭）
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_async_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """基于引擎创建 AsyncSession 工厂。"""
    return async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


@asynccontextmanager
async def session_scope(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """标准化事务作用域：自动提交/回滚与资源释放。"""
    session = sessionmaker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
