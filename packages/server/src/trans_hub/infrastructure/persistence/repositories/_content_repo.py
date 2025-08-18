# packages/server/src/trans_hub/infrastructure/persistence/repositories/_content_repo.py
"""内容仓库的 SQLAlchemy 实现。"""

from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy import select, update, func
from trans_hub.infrastructure.db._schema import ThContent
from trans_hub_core.uow import IContentRepository
from ._base_repo import BaseRepository


class SqlAlchemyContentRepository(BaseRepository, IContentRepository):
    """内容仓库实现。"""

    async def add(self, **data: Any) -> str:
        """
        添加一个新的内容记录。
        如果 data 中包含 id，则使用它；否则，生成一个新的 UUID。
        """
        # [修复] 优先使用传入的 id
        if "id" not in data:
            data["id"] = str(uuid.uuid4())

        content = ThContent(**data)
        self._session.add(content)
        await self._session.flush()
        return content.id

    async def get_id_by_uida(
        self, project_id: str, namespace: str, keys_sha256_bytes: bytes
    ) -> str | None:
        stmt = select(ThContent.id).where(
            ThContent.project_id == project_id,
            ThContent.namespace == namespace,
            ThContent.keys_sha256_bytes == keys_sha256_bytes,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update_payload(self, content_id: str, payload: dict[str, Any]) -> None:
        stmt = (
            update(ThContent)
            .where(ThContent.id == content_id)
            .values(source_payload_json=payload, updated_at=func.now())
        )
        await self._session.execute(stmt)
