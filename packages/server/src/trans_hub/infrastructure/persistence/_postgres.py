# packages/server/src/trans_hub/infrastructure/persistence/_postgres.py
"""
`PersistenceHandler` 协议的 PostgreSQL 实现。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from trans_hub_core.exceptions import DatabaseError
from trans_hub_core.types import ContentItem

from ._base import BasePersistenceHandler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = structlog.get_logger(__name__)

class PostgresPersistenceHandler(BasePersistenceHandler):
    """PostgreSQL 持久化处理器。"""
    # ... (代码与上次提供的 `_postgres.py` 最终版一致) ...

    async def stream_draft_translations(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """使用 `FOR UPDATE SKIP LOCKED` 并发安全地流式获取任务。"""
        while True:
            async with self._sessionmaker.begin() as session:
                head_results = await self._stream_drafts_query(session, batch_size, for_update=True, skip_locked=True)
                if not head_results:
                    break
                
                items = await self._build_content_items_from_orm(session, head_results)
                if not items:
                    break
                
                yield items