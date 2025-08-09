# trans_hub/persistence/sqlite.py
"""提供了基于 aiosqlite 的持久化实现。"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import ThTranslations
from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """`PersistenceHandler` 协议的 SQLite 实现。"""

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

    async def stream_draft_translations(
        self,
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """[实现] 为 SQLite 实现简单的流式获取。"""
        processed_count = 0
        while limit is None or processed_count < limit:
            current_batch_size = (
                min(batch_size, limit - processed_count)
                if limit is not None
                else batch_size
            )
            if current_batch_size <= 0:
                break
            
            async with self._sessionmaker.begin() as session:
                stmt = (
                    select(ThTranslations)
                    .where(ThTranslations.status == TranslationStatus.DRAFT.value)
                    .order_by(ThTranslations.created_at)
                    .limit(current_batch_size)
                )
                orm_results = (await session.execute(stmt)).scalars().all()
                if not orm_results:
                    break
                
                # SQLite 不支持 SKIP LOCKED，所以这里没有并发保护。
                # 这在测试或单-worker 场景下是可接受的。
                items = await self._build_content_items_from_orm(session, orm_results)

            if not items:
                break
            
            yield items
            processed_count += len(items)

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] SQLite 不支持 LISTEN/NOTIFY。"""
        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False:
                yield ""
        return _empty_generator()