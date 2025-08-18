# packages/server/src/trans_hub/infrastructure/persistence/_postgres.py
"""
`PersistenceHandler` 协议的 PostgreSQL 实现。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text

from trans_hub_core.types import ContentItem, TranslationStatus

from ._base import BasePersistenceHandler
from ._statements import PostgresStatementFactory
from trans_hub.infrastructure.db._schema import ThTransHead

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


logger = structlog.get_logger(__name__)


class PostgresPersistenceHandler(BasePersistenceHandler):
    """PostgreSQL 持久化处理器。"""

    def __init__(self, sessionmaker: Any, dsn: str):
        super().__init__(sessionmaker, stmt_factory=PostgresStatementFactory())
        self.dsn = dsn
        logger.debug("PostgreSQL 持久化处理器已初始化")

    async def connect(self) -> None:
        """检查与 PostgreSQL 数据库的连接。"""
        try:
            async with self._sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            logger.info("成功连接到 PostgreSQL 数据库", db=self.dsn.split("@")[-1])
        except Exception as e:
            logger.error("无法连接到 PostgreSQL 数据库", error=str(e))
            raise

    async def stream_draft_translations(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """
        使用分页和短暂事务并发安全地流式获取 'draft' 任务。
        """
        offset = 0
        while True:
            items_to_yield = []
            
            async with self._sessionmaker.begin() as session:
                stmt = (
                    select(ThTransHead)
                    .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
                    .order_by(ThTransHead.updated_at)
                    .limit(batch_size)
                    .offset(offset)
                    .with_for_update(skip_locked=True)
                )
                result = await session.execute(stmt)
                head_results = list(result.scalars().all())

                if not head_results:
                    break

                items_to_yield = await self._build_content_items_from_orm(session, head_results)
                
                if not items_to_yield:
                    break

            yield items_to_yield

            if len(items_to_yield) < batch_size:
                break
            
            offset += batch_size