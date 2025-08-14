# packages/server/src/trans_hub/infrastructure/persistence/_sqlite.py
"""
`PersistenceHandler` 协议的 SQLite 实现。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from trans_hub_core.types import ContentItem

from ._base import BasePersistenceHandler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """SQLite 持久化处理器。"""

    def __init__(self, sessionmaker: Any):
        super().__init__(sessionmaker)
        logger.debug("SQLite 持久化处理器已初始化")

    async def connect(self) -> None:
        """检查与 SQLite 数据库的连接。"""
        try:
            async with self._sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            logger.info("成功连接到 SQLite 数据库")
        except Exception as e:
            logger.error("无法连接到 SQLite 数据库", error=str(e))
            raise

    def _get_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        """
        为 SQLite 生成一个 `INSERT ... ON CONFLICT ... DO UPDATE` 语句。
        """
        stmt = sqlite_insert(model).values(**values)
        if update_cols:
            update_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            # 确保 updated_at 总是被更新
            if "updated_at" in [c.name for c in model.__table__.columns]:
                update_dict["updated_at"] = func.now()

            stmt = stmt.on_conflict_do_update(
                index_elements=index_elements,
                set_=update_dict,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)

        return stmt

    async def stream_draft_translations(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """为 SQLite 实现一个简化的、非并发安全的流式获取方法。"""
        offset = 0
        while True:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTransHead)
                    .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
                    .order_by(ThTransHead.updated_at)
                    .limit(batch_size)
                    .offset(offset)
                )
                head_results = (await session.execute(stmt)).scalars().all()

            if not head_results:
                break

            items = await self._build_content_items_from_orm(session, head_results)
            yield items

            if len(head_results) < batch_size:
                break
            offset += batch_size
