# trans_hub/persistence/sqlite.py
# [v2.4 Refactor] 更新 SQLite 实现，适配 rev/head 模型。
# 核心：stream_draft_translations 实现无死锁的两阶段查询。
from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import ThTransHead
from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """`PersistenceHandler` 协议的 SQLite 实现。"""

    SUPPORTS_NOTIFICATIONS = False

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], db_path: str):
        super().__init__(sessionmaker, is_sqlite=True)
        self.db_path = db_path

    async def connect(self) -> None:
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
        all_draft_head_ids: list[str] = []
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTransHead.id).where(
                    ThTransHead.current_status == TranslationStatus.DRAFT.value
                ).order_by(ThTransHead.updated_at)
                if limit:
                    stmt = stmt.limit(limit)
                all_draft_head_ids = (await session.execute(stmt)).scalars().all()
        except Exception as e:
            raise DatabaseError("为 SQLite 获取草稿 ID 失败。") from e

        for i in range(0, len(all_draft_head_ids), batch_size):
            id_batch = all_draft_head_ids[i:i + batch_size]
            items: list[ContentItem] = []
            try:
                async with self._sessionmaker() as session:
                    stmt = select(ThTransHead).where(ThTransHead.id.in_(id_batch))
                    head_results = (await session.execute(stmt)).scalars().all()
                    items = await self._build_content_items_from_orm(session, head_results)
            except Exception:
                logger.error("为批次获取完整内容失败", batch_ids=id_batch, exc_info=True)
                continue
            
            if items:
                yield items

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False: yield ""
        return _empty_generator()