# packages/server/src/trans_hub/application/services/_revision_lifecycle.py
"""修订生命周期管理的应用服务。"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import update

from trans_hub.infrastructure.db._schema import ThTransHead, ThTransRev
from trans_hub_core.types import TranslationStatus
from ..events import TranslationPublished, TranslationRejected, TranslationUnpublished

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    from trans_hub.infrastructure.uow import UowFactory
    from ._event_publisher import EventPublisher


class RevisionLifecycleService:
    def __init__(self, uow_factory: UowFactory, config: TransHubConfig, event_publisher: EventPublisher):
        self._uow_factory = uow_factory
        self._config = config
        self._event_publisher = event_publisher

    async def publish(self, revision_id: str, actor: str) -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj or rev_obj.status != TranslationStatus.REVIEWED:
                return False

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if not head_obj:
                return False

            # 直接使用 session 执行更新，保持现有逻辑
            # 注意：这里我们直接操作 ORM 对象也可以，但 execute 更直接
            session = getattr(uow, "session", None)
            if not session:
                raise TypeError("UoW is missing a 'session' attribute.")

            await session.execute(
                update(ThTransRev)
                .where(
                    ThTransRev.id == revision_id,
                    ThTransRev.project_id == head_obj.project_id,
                )
                .values(status=TranslationStatus.PUBLISHED.value)
            )

            await session.execute(
                update(ThTransHead)
                .where(
                    ThTransHead.id == head_obj.id,
                    ThTransHead.project_id == head_obj.project_id,
                )
                .values(
                    published_rev_id=revision_id,
                    published_no=rev_obj.revision_no,
                    published_at=datetime.now(timezone.utc),
                    current_rev_id=revision_id,
                    current_status=TranslationStatus.PUBLISHED.value,
                    current_no=rev_obj.revision_no,
                )
            )

            await self._event_publisher.publish(
                uow,
                TranslationPublished(
                    head_id=head_obj.id,
                    project_id=head_obj.project_id,
                    actor=actor,
                    payload={"revision_id": revision_id},
                ),
            )
        return True

    async def unpublish(self, revision_id: str, actor: str) -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj or rev_obj.status != TranslationStatus.PUBLISHED:
                return False

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if not head_obj or head_obj.published_rev_id != revision_id:
                return False

            session = getattr(uow, "session", None)
            if not session:
                raise TypeError("UoW is missing a 'session' attribute.")

            await session.execute(
                update(ThTransRev)
                .where(
                    ThTransRev.id == revision_id,
                    ThTransRev.project_id == head_obj.project_id,
                )
                .values(status=TranslationStatus.REVIEWED.value)
            )

            await session.execute(
                update(ThTransHead)
                .where(
                    ThTransHead.id == head_obj.id,
                    ThTransHead.project_id == head_obj.project_id,
                )
                .values(
                    published_rev_id=None,
                    published_no=None,
                    published_at=None,
                    current_status=TranslationStatus.REVIEWED.value,
                )
            )

            await self._event_publisher.publish(
                uow,
                TranslationUnpublished(
                    head_id=head_obj.id,
                    project_id=head_obj.project_id,
                    actor=actor,
                    payload={"revision_id": revision_id},
                ),
            )
        return True

    async def reject(self, revision_id: str, actor: str) -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj:
                return False

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if not head_obj:
                return False

            session = getattr(uow, "session", None)
            if not session:
                raise TypeError("UoW is missing a 'session' attribute.")

            result = await session.execute(
                update(ThTransRev)
                .where(
                    ThTransRev.id == revision_id,
                    ThTransRev.project_id == head_obj.project_id,
                )
                .values(status=TranslationStatus.REJECTED.value)
            )
            if result.rowcount == 0:
                return False

            await session.execute(
                update(ThTransHead)
                .where(
                    ThTransHead.current_rev_id == revision_id,
                    ThTransHead.project_id == head_obj.project_id,
                )
                .values(current_status=TranslationStatus.REJECTED.value)
            )

            await self._event_publisher.publish(
                uow,
                TranslationRejected(
                    head_id=head_obj.id,
                    project_id=head_obj.project_id,
                    actor=actor,
                    payload={"revision_id": revision_id},
                ),
            )
        return True
