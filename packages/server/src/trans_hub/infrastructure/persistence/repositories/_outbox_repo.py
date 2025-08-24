# packages/server/src/trans_hub/infrastructure/persistence/repositories/_outbox_repo.py
"""事务性发件箱仓库的 SQLAlchemy 实现。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from trans_hub.infrastructure.db._schema import ThOutboxEvents
from trans_hub_core.uow import IOutboxRepository

from ._base_repo import BaseRepository


class SqlAlchemyOutboxRepository(BaseRepository, IOutboxRepository):
    """发件箱仓库实现。"""

    # [修复] 更新方法签名以匹配协议，并使用所有必需字段
    async def add(
        self, *, project_id: str, event_id: str, topic: str, payload: dict[str, Any]
    ) -> None:
        event = ThOutboxEvents(
            project_id=project_id,
            event_id=event_id,
            topic=topic,
            payload=payload,
        )
        self._session.add(event)

    async def pull_pending(self, batch_size: int) -> list[ThOutboxEvents]:
        stmt = (
            select(ThOutboxEvents)
            .where(ThOutboxEvents.status == "pending")
            .order_by(ThOutboxEvents.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_published(self, event_ids: list[uuid.UUID]) -> None:
        stmt = (
            update(ThOutboxEvents)
            .where(ThOutboxEvents.id.in_(event_ids))
            .values(status="published", published_at=func.now())
        )
        await self._session.execute(stmt)
