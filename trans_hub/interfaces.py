# trans_hub/interfaces.py (v1.1 修正版)
"""
trans_hub/interfaces.py

本模块使用 typing.Protocol 定义了核心组件的接口（或称协议）。
此版本已根据最终版文档的术语和数据传输对象（DTOs）进行更新，
并包含了对事务管理和垃圾回收参数的协议扩展。
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import AbstractContextManager
from typing import (
    Any,
    Optional,
    Protocol,
)

# 导入 AbstractContextManager 用于事务上下文
from trans_hub.types import (
    ContentItem,
    SourceUpdateResult,
    TranslationResult,
    TranslationStatus,
)

# ==============================================================================
#  持久化处理器接口 (Persistence Handler Protocols)
# ==============================================================================


class PersistenceHandler(Protocol):
    """同步持久化处理器的接口协议。"""

    def update_or_create_source(
        self,
        text_content: str,
        business_id: str,
        context_hash: str,  # <-- 修正点：改为 str
    ) -> SourceUpdateResult:
        """根据 business_id 更新或创建一个源记录。
        参数 `text` 已更名为 `text_content` 以保持命名一致性。
        """
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Generator[list[ContentItem], None, None]:
        """以流式方式获取待翻译的内容批次。"""
        ...

    def save_translations(self, results: list[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """根据文本内容、目标语言和上下文，从数据库中获取已翻译的结果。"""
        ...

    def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]:  # <-- 修正点：添加新方法
        """根据 content_id 和 context_hash 从 th_sources 表获取 business_id。"""
        ...

    def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        ...

    def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...

    def transaction(
        self,
    ) -> AbstractContextManager[
        Any
    ]:  # <-- 修正点：使用 contextlib.AbstractContextManager
        """提供一个同步数据库事务上下文管理器。"""
        ...

    def touch_source(self, business_id: str) -> None:
        """更新指定 business_id 的 last_seen_at 时间戳到当前时间。"""
        ...


class AsyncPersistenceHandler(Protocol):
    """异步持久化处理器的接口协议。
    签名与同步版本一一对应，但所有方法都是异步的 (`async def`)。
    """

    async def update_or_create_source(
        self,
        text_content: str,
        business_id: str,
        context_hash: str,  # <-- 修正点：改为 str
    ) -> SourceUpdateResult:
        """根据 business_id 更新或创建一个源记录。"""
        ...

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """以流式方式获取待翻译的内容批次。"""
        ...

    async def save_translations(self, results: list[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """根据文本内容、目标语言和上下文，从数据库中获取已翻译的结果。"""
        ...

    async def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]:  # <-- 修正点：添加新方法
        """根据 content_id 和 context_hash 从 th_sources 表获取 business_id。"""
        ...

    async def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        ...

    async def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...

    async def transaction(
        self,
    ) -> AbstractContextManager[Any]:  # 保持 AbstractContextManager
        """提供一个异步数据库事务上下文管理器。"""
        ...
