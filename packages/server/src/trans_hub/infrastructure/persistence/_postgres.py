# packages/server/src/trans_hub/infrastructure/persistence/_postgres.py
"""
`PersistenceHandler` 协议的 PostgreSQL 实现。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, text
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from trans_hub_core.types import ContentItem, TranslationStatus

from ._base import BasePersistenceHandler
from trans_hub.infrastructure.db._schema import ThTransHead

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
        """
        [关键修复] 使用分页和短暂事务并发安全地流式获取 'draft' 任务。

        修复逻辑：
        1. 在一个独立的、短暂的事务中查询并使用 `FOR UPDATE SKIP LOCKED` 锁定一批任务。
        2. 在该事务内部，将 ORM 对象转换为 DTO (`ContentItem`)。
        3. 事务提交，立即释放行锁。
        4. 在事务外部 `yield` DTO 列表，避免在持有锁的同时将控制权交还给调用方，从而根除死锁。
        """
        offset = 0
        while True:
            items_to_yield = []
            
            # 步骤 1 & 2: 在短暂事务中获取并转换数据
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
                
                # 如果构建 DTO 后列表为空，也应终止
                if not items_to_yield:
                    break

            # 步骤 3 & 4: 事务已提交，锁已释放，现在可以安全地 yield
            yield items_to_yield

            # 如果获取到的批次小于请求大小，说明是最后一批
            if len(items_to_yield) < batch_size:
                break
            
            offset += batch_size