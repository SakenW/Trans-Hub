# packages/server/src/trans_hub/application/coordinator.py
"""
Trans-Hub 应用服务总协调器 (v3.3.1 属性修复版)。
这是一个高级门面，将调用委托给具体的应用服务。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from trans_hub_core.types import Comment

if TYPE_CHECKING:
    from .services import (
        CommentingService,
        RequestTranslationService,
        RevisionLifecycleService,
        TranslationQueryService,
    )


class Coordinator:
    """高级门面，协调所有应用服务。"""

    def __init__(
        self,
        request_service: RequestTranslationService,
        lifecycle_service: RevisionLifecycleService,
        commenting_service: CommentingService,
        query_service: TranslationQueryService,
    ):
        self.request_service = request_service
        self.lifecycle_service = lifecycle_service
        self.commenting_service = commenting_service
        self.query_service = query_service

    async def request_translation(self, **kwargs: Any) -> str:
        return await self.request_service.execute(**kwargs)

    async def get_translation(self, **kwargs: Any) -> dict[str, Any] | None:
        return await self.query_service.execute(**kwargs)

    async def publish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        return await self.lifecycle_service.publish(revision_id, actor)

    async def unpublish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        return await self.lifecycle_service.unpublish(revision_id, actor)

    async def reject_translation(self, revision_id: str, actor: str = "system") -> bool:
        return await self.lifecycle_service.reject(revision_id, actor)

    async def add_comment(self, head_id: str, author: str, body: str) -> str:
        return await self.commenting_service.add(head_id, author, body)

    async def get_comments(self, head_id: str) -> list[Comment]:
        return await self.commenting_service.get_all(head_id)

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass
