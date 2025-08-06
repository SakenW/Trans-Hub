# trans_hub/core/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口协议。
v3.0.0.dev: 重构以适应新的数据模型，并为可插拔的持久层设计。
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from trans_hub.core.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)


@dataclass
class TranslationNotification:
    """表示一个翻译任务通知。"""

    translation_id: str
    content_id: str
    target_lang: str
    source_payload: dict[str, Any]
    business_id: str | None = None
    context_id: str | None = None
    context: dict[str, Any] | None = None


class PersistenceHandler(Protocol):
    """定义了持久化处理器的纯异步接口协议。"""

    SUPPORTS_NOTIFICATIONS: bool = False

    async def connect(self) -> None:
        """建立与数据库的连接。"""
        ...

    async def close(self) -> None:
        """关闭与数据库的连接。"""
        ...

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[可选] 监听数据库通知，返回通知的负载。"""
        ...

    async def reset_stale_tasks(self) -> None:
        """在启动时重置所有处于“TRANSLATING”状态的旧任务为“PENDING”。"""
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]: ...

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> tuple[str, str | None]: ...

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: str | None,
        target_langs: list[str],
        source_lang: str | None,
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None: ...

    async def save_translation_results(
        self,
        results: list[TranslationResult],
    ) -> None: ...

    async def find_translation(
        self,
        business_id: str,
        target_lang: str,
        context: dict[str, Any] | None = None,
    ) -> TranslationResult | None: ...

    async def garbage_collect(
        self,
        retention_days: int,
        dry_run: bool = False,
        _now: datetime | None = None,
    ) -> dict[str, int]: ...

    async def move_to_dlq(
        self,
        item: ContentItem,
        target_lang: str,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None: ...
