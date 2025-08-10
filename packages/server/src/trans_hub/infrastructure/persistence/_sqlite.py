# packages/server/src/trans_hub/infrastructure/persistence/_sqlite.py
"""
`PersistenceHandler` 协议的 SQLite 实现。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import insert, text

from ._base import BasePersistenceHandler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from trans_hub_core.types import ContentItem

logger = structlog.get_logger(__name__)

class SQLitePersistenceHandler(BasePersistenceHandler):
    """SQLite 持久化处理器。"""
    # ... (代码与上次提供的 `_sqlite.py` 最终版一致) ...

    async def stream_draft_translations(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """为 SQLite 实现一个简化的、非并发安全的流式获取方法。"""
        async with self._sessionmaker() as session:
            all_heads = await self._stream_drafts_query(session, 1000)

        for i in range(0, len(all_heads), batch_size):
            head_batch = all_heads[i : i + batch_size]
            async with self._sessionmaker() as session:
                items = await self._build_content_items_from_orm(session, head_batch)
                if items:
                    yield items