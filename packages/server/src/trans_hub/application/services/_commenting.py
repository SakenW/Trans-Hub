# packages/server/src/trans_hub/application/services/_commenting.py
"""评论相关的应用服务。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from trans_hub_core.types import Comment

from ..events import CommentAdded

if TYPE_CHECKING:
    from trans_hub.infrastructure.uow import UowFactory

    from ._event_publisher import EventPublisher


class CommentingService:
    def __init__(self, uow_factory: UowFactory, event_publisher: EventPublisher):
        self._uow_factory = uow_factory
        self._event_publisher = event_publisher

    async def add(self, head_id: str, author: str, body: str) -> str:
        async with self._uow_factory() as uow:
            head = await uow.translations.get_head_by_id(head_id)
            if not head:
                raise ValueError(f"翻译头 ID '{head_id}' 不存在。")

            comment = Comment(
                head_id=head_id, project_id=head.project_id, author=author, body=body
            )
            comment_id = await uow.misc.add_comment(comment)

            await self._event_publisher.publish(
                uow,
                CommentAdded(
                    head_id=head_id,
                    project_id=head.project_id,
                    comment_id=comment_id,
                    actor=author,
                    payload={"comment_id": comment_id},
                ),
            )
            await uow.commit()  # 手动提交以确保 comment_id 在事件发布前可用
        return comment_id

    async def get_all(self, head_id: str) -> list[Comment]:
        async with self._uow_factory() as uow:
            return await uow.misc.get_comments(head_id)
