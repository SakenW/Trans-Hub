# trans_hub/persistence/postgres.py
"""提供了基于 asyncpg 的持久化实现。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

try:
    import asyncpg
except ImportError:
    asyncpg = None

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import ThTranslations
from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class PostgresPersistenceHandler(BasePersistenceHandler):
    """
    `PersistenceHandler` 协议的 PostgreSQL 实现。
    包含方言特有的连接、通知和 `SKIP LOCKED` 优化。
    """

    SUPPORTS_NOTIFICATIONS = True
    NOTIFICATION_CHANNEL = "new_translation_draft"

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], dsn: str):
        super().__init__(sessionmaker)
        self.dsn = dsn
        self._notification_listener_conn: asyncpg.Connection | None = None
        self._notification_queue: asyncio.Queue[str] | None = None

    async def connect(self) -> None:
        """[覆盖] 健康检查以确保 PostgreSQL 连接正常。"""
        try:
            async with self._sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            logger.info("PostgreSQL 数据库连接已建立并通过健康检查")
        except Exception as e:
            logger.error("连接 PostgreSQL 数据库失败", exc_info=True)
            raise DatabaseError(f"数据库连接失败: {e}") from e

    async def close(self) -> None:
        """[覆盖] 关闭通用连接池，并额外清理通知监听器。"""
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
        if (
            self._notification_listener_conn
            and not self._notification_listener_conn.is_closed()
        ):
            await self._notification_listener_conn.close()
        await super().close()
        logger.info("PostgreSQL 持久层资源已完全关闭")

    async def stream_draft_translations(
        self,
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """[实现] 为 PostgreSQL 实现使用 SKIP LOCKED 的高性能版本。"""
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
                    .with_for_update(skip_locked=True)
                )
                orm_results = (await session.execute(stmt)).scalars().all()
                if not orm_results:
                    break
                
                # 在 PG 中，被选中的行已被锁定，可以安全构建 ContentItem
                items = await self._build_content_items_from_orm(session, orm_results)

            if not items:
                break
            
            yield items
            processed_count += len(items)

    async def _notification_callback(self, payload: str) -> None:
        if self._notification_queue:
            await self._notification_queue.put(payload)

    async def _listen_loop(self) -> None:
        connect_dsn = self.dsn.replace("postgresql+asyncpg", "postgresql", 1)
        try:
            assert asyncpg is not None
            self._notification_listener_conn = await asyncpg.connect(dsn=connect_dsn)
            await self._notification_listener_conn.add_listener(
                self.NOTIFICATION_CHANNEL,
                lambda c, p, ch, pl: asyncio.create_task(self._notification_callback(pl))
            )
            logger.info("PostgreSQL 通知监听器已启动", channel=self.NOTIFICATION_CHANNEL)
            # Loop forever
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("PostgreSQL 通知监听器正在关闭。")
        finally:
            if self._notification_listener_conn and not self._notification_listener_conn.is_closed():
                await self._notification_listener_conn.close()
            self._notification_listener_conn = None

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] PostgreSQL 特有的 LISTEN/NOTIFY 机制。"""
        async def _internal_generator() -> AsyncGenerator[str, None]:
            if not self._notification_task:
                 self._notification_queue = asyncio.Queue()
                 self._notification_task = asyncio.create_task(self._listen_loop())
            
            assert self._notification_queue is not None
            while True:
                try:
                    payload = await self._notification_queue.get()
                    yield payload
                except asyncio.CancelledError:
                    break
        return _internal_generator()