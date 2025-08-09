# trans_hub/persistence/sqlite.py
"""提供了基于 aiosqlite 的、高度简化的持久化实现。"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """
    `PersistenceHandler` 协议的 SQLite 实现。
    只包含 SQLite 方言特有的 PRAGMA 设置逻辑。
    """

    SUPPORTS_NOTIFICATIONS = False

    def __init__(self, sessionmaker: async_sessionmaker, db_path: str):
        super().__init__(sessionmaker)
        self.db_path = db_path

    async def connect(self) -> None:
        """[覆盖] 建立连接并为 SQLite 设置必要的 PRAGMA。"""
        async with self._sessionmaker() as session:
            async with session.begin():
                await session.execute(text("PRAGMA foreign_keys = ON;"))
                if self.db_path != ":memory:":
                    await session.execute(text("PRAGMA journal_mode=WAL;"))
        logger.info("SQLite 数据库连接已建立并通过 PRAGMA 检查", db_path=self.db_path)

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] SQLite 不支持 LISTEN/NOTIFY。"""

        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False:
                yield ""

        return _empty_generator()