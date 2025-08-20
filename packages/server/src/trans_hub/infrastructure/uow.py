# packages/server/src/trans_hub/infrastructure/uow.py
"""
SQLAlchemy 单元工作 (Unit of Work) 的具体实现。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from trans_hub_core.uow import IUnitOfWork
from .persistence.repositories import (
    SqlAlchemyContentRepository,
    SqlAlchemyTranslationRepository,
    SqlAlchemyTmRepository,
    SqlAlchemyMiscRepository,
    SqlAlchemyOutboxRepository,  # [修复] 导入 Outbox 仓库
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """SQLAlchemy UoW 实现。"""

    def __init__(self, sessionmaker: "async_sessionmaker[AsyncSession]"):
        self._sessionmaker = sessionmaker
        self.session: "AsyncSession"

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._sessionmaker()
        self.content = SqlAlchemyContentRepository(self.session)
        self.translations = SqlAlchemyTranslationRepository(self.session)
        self.tm = SqlAlchemyTmRepository(self.session)
        self.misc = SqlAlchemyMiscRepository(self.session)
        self.outbox = SqlAlchemyOutboxRepository(self.session)  # [修复] 补全实例化
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


# 类型别名，用于依赖注入
UowFactory = Callable[[], IUnitOfWork]