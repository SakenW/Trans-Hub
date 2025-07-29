# trans_hub/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口协议。
v3.0 更新：ID类型已从 int 切换为 str (UUID)，并增加了 touch_jobs 方法。
"""

from collections.abc import AsyncGenerator
from typing import Any, Optional, Protocol

from trans_hub.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)


class PersistenceHandler(Protocol):
    """定义了持久化处理器的纯异步接口协议。"""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def reset_stale_tasks(self) -> None: ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]: ...

    async def ensure_pending_translations(
        self,
        text_content: str,
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        business_id: Optional[str] = None,
        context_hash: Optional[str] = None,
        context_json: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None: ...

    async def save_translations(self, results: list[TranslationResult]) -> None: ...

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]: ...

    async def get_business_id_for_job(
        self, content_id: str, context_id: Optional[str]
    ) -> Optional[str]: ...

    async def touch_jobs(self, business_ids: list[str]) -> None: ...

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]: ...

    async def move_to_dlq(
        self,
        item: ContentItem,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None: ...
