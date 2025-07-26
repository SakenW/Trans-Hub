# trans_hub/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口。
此版本为纯异步设计，并强化了封装性。
"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, Optional, Protocol

import aiosqlite  # 导入以用于类型提示

from trans_hub.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)


class PersistenceHandler(Protocol):
    """持久化处理器的纯异步接口协议。"""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    def transaction(self) -> AbstractAsyncContextManager[aiosqlite.Cursor]: ...

    async def reset_stale_tasks(self) -> None: ...  # 新增：自愈机制接口

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
        force_retranslate: bool = False,  # 新增：强制重翻参数
    ) -> None: ...
    async def save_translations(self, results: list[TranslationResult]) -> None: ...
    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]: ...
    async def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]: ...
    async def touch_source(self, business_id: str) -> None: ...
    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]: ...
