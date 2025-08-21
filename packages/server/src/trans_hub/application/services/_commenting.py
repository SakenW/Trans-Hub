# packages/server/src/trans_hub/application/services/_commenting.py
"""评论相关的应用服务。"""

from __future__ import annotations
from typing import TYPE_CHECKING
import uuid  # [新增]

from trans_hub_core.types import Comment, Event
from ..events import CommentAdded

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    from trans_hub.infrastructure.uow import UowFactory
    from trans_hub_core.uow import IUnitOfWork


class CommentingService:
    def __init__(self, uow_factory: UowFactory, config: TransHubConfig):
        self._uow_factory = uow_factory
        self._config = config

    async def add(self, head_id: str, author: str, body: str) -> str:
        async with self._uow_factory() as uow:
            head = await uow.translations.get_head_by_id(head_id)
            if not head:
                raise ValueError(f"翻译头 ID '{head_id}' 不存在。")

            comment = Comment(
                head_id=head_id, project_id=head.project_id, author=author, body=body
            )
            comment_id = await uow.misc.add_comment(comment)

            await self._publish_event(
                uow,
                CommentAdded(
                    head_id=head_id,
                    project_id=head.project_id,
                    actor=author,
                    payload={"comment_id": comment_id},
                ),
            )
            # [修复] 手动提交，因为事件发布后需要 comment_id，所以不能等 UoW 自动提交
            await uow.commit()
        return comment_id

    async def get_all(self, head_id: str) -> list[Comment]:
        async with self._uow_factory() as uow:
            return await uow.misc.get_comments(head_id)

    async def _publish_event(self, uow: IUnitOfWork, event: Event) -> None:
        # [修复] 传递 project_id 和 event_id
        await uow.outbox.add(
            project_id=event.project_id,
            event_id=str(uuid.uuid4()),
            topic=self._config.worker.event_stream_name,
            payload=event.model_dump(mode="json"),
        )
