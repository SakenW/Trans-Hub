# trans_hub/persistence/postgres.py
"""提供了基于 asyncpg 的、高度简化的持久化实现。"""
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
    只包含方言特有的连接、通知和 `SKIP LOCKED` 优化。
    """

    SUPPORTS_NOTIFICATIONS = True
    NOTIFICATION_CHANNEL = "new_translation_task"

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
        if (
            self._notification_listener_conn
            and not self._notification_listener_conn.is_closed()
        ):
            try:
                await self._notification_listener_conn.remove_listener(
                    self.NOTIFICATION_CHANNEL, self._notification_callback
                )
            except (asyncpg.InterfaceError, asyncpg.PostgresError):
                pass
            await self._notification_listener_conn.close()
            self._notification_listener_conn = None
        
        await super().close()
        logger.info("PostgreSQL 持久层资源已完全关闭")

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """[覆盖] 为 PostgreSQL 实现使用 SKIP LOCKED 的高性能版本。"""
        processed_count = 0
        status_values = [s.value for s in statuses]
        while limit is None or processed_count < limit:
            current_batch_size = min(
                batch_size,
                (limit - processed_count) if limit is not None else batch_size,
            )
            if current_batch_size <= 0:
                break
            
            items: list[ContentItem] = []
            
            async with self._sessionmaker.begin() as session:
                stmt = (
                    select(ThTranslations)
                    .where(
                        ThTranslations.target_lang == lang_code,
                        ThTranslations.status.in_(status_values),
                    )
                    .order_by(ThTranslations.created_at)
                    .limit(current_batch_size)
                    .with_for_update(skip_locked=True)
                )
                
                orm_results = (await session.execute(stmt)).scalars().all()
                if not orm_results:
                    break

                for orm_obj in orm_results:
                    orm_obj.status = "translating"
                await session.flush()
                
                items = await self._build_content_items_from_orm(session, orm_results)

            if not items:
                break
            yield items
            processed_count += len(items)

    async def _notification_callback(
        self, connection: asyncpg.Connection, pid: int, channel: str, payload: str
    ) -> None:
        if self._notification_queue:
            await self._notification_queue.put(payload)

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] PostgreSQL 特有的 LISTEN/NOTIFY 机制。"""
        async def _internal_generator() -> AsyncGenerator[str, None]:
            connect_dsn = self.dsn.replace("postgresql+asyncpg", "postgresql", 1)
            try:
                if (
                    not self._notification_listener_conn
                    or self._notification_listener_conn.is_closed()
                ):
                    assert asyncpg is not None
                    self._notification_listener_conn = await asyncpg.connect(dsn=connect_dsn)
                    self._notification_queue = asyncio.Queue()
                    await self._notification_listener_conn.add_listener(
                        self.NOTIFICATION_CHANNEL, self._notification_callback
                    )
                    logger.info("PostgreSQL 通知监听器已启动", channel=self.NOTIFICATION_CHANNEL)
                
                assert self._notification_queue is not None
                while True:
                    payload = await self._notification_queue.get()
                    yield payload
            finally:
                logger.warning("PostgreSQL 通知监听器正在关闭和清理资源...")
                if self._notification_listener_conn and not self._notification_listener_conn.is_closed():
                    try:
                        await self._notification_listener_conn.remove_listener(
                            self.NOTIFICATION_CHANNEL, self._notification_callback
                        )
                    except (asyncpg.InterfaceError, asyncpg.PostgresError):
                        pass
                    await self._notification_listener_conn.close()
                self._notification_listener_conn = None
                self._notification_queue = None
                logger.info("PostgreSQL 通知监听器资源已成功清理。")

        return _internal_generator()