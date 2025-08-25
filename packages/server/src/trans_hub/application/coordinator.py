# packages/server/src/trans_hub/application/coordinator.py
"""
Trans-Hub 应用服务总协调器 (v3.3.1 依赖注入修复版)。
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
    """[修复] 高级门面，接收已初始化的服务实例。"""

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
        """提交一个新的翻译请求。"""
        return await self.request_service.execute(**kwargs)

    async def get_translation(self, **kwargs: Any) -> dict[str, Any] | None:
        """获取已发布的翻译，应用回退逻辑。"""
        return await self.query_service.execute(**kwargs)

    async def publish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        """发布一个 'reviewed' 状态的修订。"""
        return await self.lifecycle_service.publish(revision_id, actor)

    async def unpublish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        """撤回一个已发布的修订。"""
        return await self.lifecycle_service.unpublish(revision_id, actor)

    async def reject_translation(self, revision_id: str, actor: str = "system") -> bool:
        """拒绝一个修订。"""
        return await self.lifecycle_service.reject(revision_id, actor)

    async def add_comment(self, head_id: str, author: str, body: str) -> str:
        """为翻译头添加评论。"""
        return await self.commenting_service.add(head_id, author, body)

    async def get_comments(self, head_id: str) -> list[Comment]:
        """获取指定翻译头的所有评论。"""
        return await self.commenting_service.get_all(head_id)
