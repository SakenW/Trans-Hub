# packages/server/src/trans_hub/application/events.py
"""
定义了 Trans-Hub 系统中所有业务事件的数据模型。

这些模型用于在系统内部（例如，通过 Redis Streams）传递结构化的事件数据，
并用于持久化到 `th_trans_events` 表中。
"""

from typing import Any

from trans_hub_core.types import Event


class TranslationSubmitted(Event):
    """当一个新的翻译请求被提交时触发。"""

    event_type: str = "translation.submitted"
    payload: dict[str, Any] | None = None


class TMApplied(Event):
    """当翻译记忆库 (TM) 成功命中并应用时触发。"""

    event_type: str = "translation.tm_applied"
    payload: dict[str, str]  # e.g., {"tm_id": "..."}


class TranslationPublished(Event):
    """当一个翻译修订被发布时触发。"""

    event_type: str = "translation.published"
    payload: dict[str, str]  # e.g., {"revision_id": "..."}


class TranslationRejected(Event):
    """当一个翻译修订被拒绝时触发。"""

    event_type: str = "translation.rejected"
    payload: dict[str, str]  # e.g., {"revision_id": "..."}


class CommentAdded(Event):
    """当一条新的评论被添加时触发。"""

    event_type: str = "translation.comment_added"
    payload: dict[str, str]  # e.g., {"comment_id": "..."}
