# packages/server/src/trans_hub/infrastructure/persistence/repositories/_misc_repo.py
"""杂项实体（项目、事件、评论、回退）仓库的 SQLAlchemy 实现。"""

from __future__ import annotations

from sqlalchemy import select

# [修复] 导入特定方言的 insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from trans_hub.infrastructure.db._schema import (
    ThComments,
    ThEvents,
    ThLocalesFallbacks,
    ThProjects,
)
from trans_hub_core.types import Comment, Event
from trans_hub_core.uow import IMiscRepository
from ._base_repo import BaseRepository


class SqlAlchemyMiscRepository(BaseRepository, IMiscRepository):
    """杂项仓库实现。"""

    def _get_insert_stmt(self):
        """[新增] 根据当前会话的方言，返回正确的 insert 函数。"""
        if self._session.bind.dialect.name == "postgresql":
            return pg_insert
        else:
            return sqlite_insert

    async def add_project_if_not_exists(
        self, project_id: str, display_name: str
    ) -> None:
        insert = self._get_insert_stmt()
        stmt = (
            insert(ThProjects)
            .values(project_id=project_id, display_name=display_name)
            .on_conflict_do_nothing(index_elements=["project_id"])
        )
        await self._session.execute(stmt)

    async def write_event(self, event: Event) -> None:
        db_event = ThEvents(**event.model_dump(exclude_none=True, exclude={"id"}))
        self._session.add(db_event)

    async def add_comment(self, comment: Comment) -> str:
        db_comment = ThComments(**comment.model_dump(exclude={"id", "created_at"}))
        self._session.add(db_comment)
        await self._session.flush()
        return str(db_comment.id)

    async def get_comments(self, head_id: str) -> list[Comment]:
        results = (
            (
                await self._session.execute(
                    select(ThComments)
                    .where(ThComments.head_id == head_id)
                    .order_by(ThComments.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [Comment.from_orm_model(r) for r in results]

    async def get_fallback_order(
        self, project_id: str, locale: str
    ) -> list[str] | None:
        return (
            await self._session.execute(
                select(ThLocalesFallbacks.fallback_order).where(
                    ThLocalesFallbacks.project_id == project_id,
                    ThLocalesFallbacks.locale == locale,
                )
            )
        ).scalar_one_or_none()

    async def set_fallback_order(
        self, project_id: str, locale: str, fallback_order: list[str]
    ) -> None:
        insert = self._get_insert_stmt()
        stmt = insert(ThLocalesFallbacks).values(
            project_id=project_id, locale=locale, fallback_order=fallback_order
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["project_id", "locale"],
            set_={"fallback_order": stmt.excluded.fallback_order},
        )
        await self._session.execute(stmt)
