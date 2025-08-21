# packages/server/src/trans_hub/infrastructure/persistence/repositories/_content_repo.py
"""内容仓库的 SQLAlchemy 实现。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from trans_hub.infrastructure.db._schema import ThContent
from trans_hub_core.uow import IContentRepository

from ._base_repo import BaseRepository


class SqlAlchemyContentRepository(BaseRepository, IContentRepository):
    """内容仓库实现。"""

    async def add(self, **data: Any) -> str:
        """
        添加一个新的内容记录。
        - 允许外部传入 id；若未传入则自动生成。
        - 确保 source_payload_json 非空，避免触发 NOT NULL 约束。
        """
        content_id = data.get("id") or str(uuid.uuid4())

        # 关键修复：保证 NOT NULL 字段有默认值
        if data.get("source_payload_json") is None:
            data["source_payload_json"] = {}

        data["id"] = content_id

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
