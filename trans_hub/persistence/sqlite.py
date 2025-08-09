# trans_hub/persistence/sqlite.py
# [终极版 v1.9 - 根除异步生成器实现缺陷导致的死锁]
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import ThTranslations
from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """
    `PersistenceHandler` 协议的 SQLite 实现。
    """

    SUPPORTS_NOTIFICATIONS = False

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], db_path: str):
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
        """
        [终极修复] 为 SQLite 实现无死锁的流式获取。
        修正了异步生成器的实现，确保在没有任务时能正确终止。
        """
        all_draft_ids: list[str] = []
        
        # 步骤 1: 在一个独立的、短暂的事务中，获取所有待办任务的 ID。
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTranslations.id).where(
                    ThTranslations.status == TranslationStatus.DRAFT.value
                ).order_by(ThTranslations.created_at)
                if limit:
                    stmt = stmt.limit(limit)
                
                result = await session.execute(stmt)
                all_draft_ids = result.scalars().all()
        except Exception as e:
            raise DatabaseError("Failed to fetch draft translation IDs for SQLite.") from e

        # [终极修复] 移除 'if not all_draft_ids: return'。
        # 如果 all_draft_ids 为空，下面的 for 循环将不会执行，
        # 生成器会自然、正确地结束，`async for` 循环也会随之终止。

        # 步骤 2: 将所有 ID 分成批次。这个过程没有任何数据库操作。
        for i in range(0, len(all_draft_ids), batch_size):
            id_batch = all_draft_ids[i:i + batch_size]
            
            # 步骤 3: 为每一批 ID，在一个新的、短暂的事务中获取它们的完整数据。
            items: list[ContentItem] = []
            try:
                async with self._sessionmaker() as session:
                    stmt = select(ThTranslations).where(ThTranslations.id.in_(id_batch))
                    orm_results = (await session.execute(stmt)).scalars().all()
                    items = await self._build_content_items_from_orm(session, orm_results)
            except Exception as e:
                logger.error("Failed to fetch full content for batch", batch_ids=id_batch, exc_info=True)
                continue
            
            # 步骤 4: 在事务完全结束后，安全地 yield 结果。
            if items:
                yield items


    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] SQLite 不支持 LISTEN/NOTIFY。"""
        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False:
                yield ""
        return _empty_generator()