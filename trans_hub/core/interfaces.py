# trans_hub/core/interfaces.py
"""
本模块使用 typing.Protocol 定义了核心组件的接口协议。
v3.0.0.dev: 重构以适应新的数据模型，并为可插拔的持久层设计。
"""

from collections.abc import AsyncGenerator
from typing import Any, Optional, Protocol

from trans_hub.core.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)


class PersistenceHandler(Protocol):
    """
    定义了持久化处理器的纯异步接口协议。
    """

    async def connect(self) -> None:
        """建立与数据库的连接。"""
        ...

    async def close(self) -> None:
        """关闭与数据库的连接。"""
        ...

    async def reset_stale_tasks(self) -> None:
        """在启动时重置所有处于“TRANSLATING”状态的旧任务为“PENDING”。"""
        ...

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """
        以流式方式获取待处理的翻译任务批次。
        """
        # 协议方法的实现由具体类提供
        if False:  # noqa: B012
            yield []

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: Optional[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        """
        确保源内容和上下文已存在于数据库中，并返回它们的内部ID。
        """
        ...

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: Optional[str],
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        """
        为给定的内容和上下文创建待处理的翻译任务。
        """
        ...

    async def save_translation_results(
        self,
        results: list[TranslationResult],
    ) -> None:
        """
        将一批已完成的翻译结果保存到数据库。
        """
        ...

    async def find_translation(
        self,
        business_id: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """
        根据稳定引用ID、目标语言和上下文，查找一个已完成的翻译。
        """
        ...

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        """
        执行垃圾回收，清理过期的、无关联的旧数据。
        """
        ...

    async def move_to_dlq(
        self,
        item: ContentItem,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None:
        """将一个无法处理的任务移动到死信队列。"""
        ...
