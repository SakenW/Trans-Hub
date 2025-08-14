# packages/server/src/trans_hub/infrastructure/persistence/_postgres.py
"""
`PersistenceHandler` 协议的 PostgreSQL 实现。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy import func
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from trans_hub_core.types import ContentItem

from ._base import BasePersistenceHandler

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


logger = structlog.get_logger(__name__)


class PostgresPersistenceHandler(BasePersistenceHandler):
    """PostgreSQL 持久化处理器。"""

    def __init__(self, sessionmaker: Any, dsn: str):
        super().__init__(sessionmaker)
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

    def _get_upsert_stmt(
        self,
        model: Any,
        values: dict[str, Any],
        index_elements: list[str],
        update_cols: list[str],
    ) -> Any:
        """
        为 PostgreSQL 生成一个 `INSERT ... ON CONFLICT ... DO UPDATE` 语句。
        """
        stmt = pg_insert(model).values(**values)
        if update_cols:
            update_dict = {
                col.name: getattr(stmt.excluded, col.name)
                for col in model.__table__.columns
                if col.name in update_cols
            }
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
        """使用 `FOR UPDATE SKIP LOCKED` 并发安全地流式获取任务。"""
        while True:
            async with self._sessionmaker.begin() as session:
                # 使用 with_for_update 实现行级锁
                head_results = await self._stream_drafts_query(
                    session, batch_size, skip_locked=True
                )
                if not head_results:
                    break

                items = await self._build_content_items_from_orm(session, head_results)
                if not items:
                    break

                yield items

                # 更新状态为 'pending' 或类似状态，防止其他 worker 重复获取
                # 此处简化为在事务结束时自动释放锁
