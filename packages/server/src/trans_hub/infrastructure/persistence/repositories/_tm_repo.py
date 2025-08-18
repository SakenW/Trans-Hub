# packages/server/src/trans_hub/infrastructure/persistence/repositories/_tm_repo.py
"""翻译记忆库仓库的 SQLAlchemy 实现。"""

from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy import select, exists, func

# [修复] 导入特定方言的 insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from trans_hub.infrastructure.db._schema import ThTmLinks, ThTmUnits
from trans_hub_core.uow import ITmRepository
from ._base_repo import BaseRepository


class SqlAlchemyTmRepository(BaseRepository, ITmRepository):
    """翻译记忆库仓库实现。"""

    def _get_insert_stmt(self):
        """[新增] 根据当前会话的方言，返回正确的 insert 函数。"""
        if self._session.bind.dialect.name == "postgresql":
            return pg_insert
        else:
            return sqlite_insert

    async def find_entry(
        self, *, project_id: str, namespace: str, reuse_sha: bytes, **kwargs: Any
    ) -> tuple[str, dict[str, Any]] | None:
        # ... (此方法不变)
        ALLOWED_FILTERS = {
            "src_lang": ThTmUnits.src_lang,
            "tgt_lang": ThTmUnits.tgt_lang,
            "variant_key": ThTmUnits.variant_key,
        }
        conditions = [
            ThTmUnits.project_id == project_id,
            ThTmUnits.namespace == namespace,
            ThTmUnits.src_hash == reuse_sha,
            ThTmUnits.approved.is_(True),
        ]
        for k, v in kwargs.items():
            if v is None:
                continue
            col = ALLOWED_FILTERS.get(k)
            if col is not None:
                conditions.append(col == v)
        stmt = (
            select(ThTmUnits.id, ThTmUnits.tgt_payload)
            .where(*conditions)
            .order_by(ThTmUnits.updated_at.desc())
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        return (str(row[0]), row[1] or {}) if row else None

    async def upsert_entry(self, **data: Any) -> str:
        values = {"id": str(uuid.uuid4()), **data}
        insert = self._get_insert_stmt()
        insert_stmt = insert(ThTmUnits).values(**values)

        # SQLite 不支持 returning，所以我们需要分开处理
        if self._session.bind.dialect.name == "postgresql":
            update_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[
                    "project_id",
                    "namespace",
                    "src_hash",
                    "tgt_lang",
                    "variant_key",
                ],
                set_={
                    "tgt_payload": insert_stmt.excluded.tgt_payload,
                    "approved": insert_stmt.excluded.approved,
                    "updated_at": func.now(),
                },
            ).returning(ThTmUnits.id)
            result = await self._session.execute(update_stmt)
            return result.scalar_one()
        else:  # SQLite
            update_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[
                    "project_id",
                    "namespace",
                    "src_hash",
                    "tgt_lang",
                    "variant_key",
                ],
                set_={
                    "tgt_payload": insert_stmt.excluded.tgt_payload,
                    "approved": insert_stmt.excluded.approved,
                    "updated_at": func.now(),
                },
            )
            await self._session.execute(update_stmt)
            # 在 SQLite 中，我们需要再做一次查询来获取 id
            select_stmt = select(ThTmUnits.id).where(
                ThTmUnits.project_id == data["project_id"],
                ThTmUnits.namespace == data["namespace"],
                ThTmUnits.src_hash == data["src_hash"],
                ThTmUnits.tgt_lang == data["tgt_lang"],
                ThTmUnits.variant_key == data["variant_key"],
            )
            result = await self._session.execute(select_stmt)
            return result.scalar_one()

    async def link_revision_to_tm(
        self, rev_id: str, tm_id: str, project_id: str
    ) -> None:
        values = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "translation_rev_id": rev_id,
            "tm_id": tm_id,
        }
        insert = self._get_insert_stmt()
        stmt = (
            insert(ThTmLinks)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["project_id", "translation_rev_id", "tm_id"]
            )
        )
        await self._session.execute(stmt)

    async def check_link_exists(self, rev_id: str) -> bool:
        stmt = select(exists().where(ThTmLinks.translation_rev_id == rev_id))
        result = await self._session.execute(stmt)
        return result.scalar() is True
