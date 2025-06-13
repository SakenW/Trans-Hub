"""trans_hub/interfaces.py (v0.1)

本模块使用 typing.Protocol 定义了核心组件的接口（或称协议）。
此版本已根据最终版文档的术语和数据传输对象（DTOs）进行更新。
"""
from typing import AsyncGenerator, Generator, List, Optional, Protocol

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
        self, text_content: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        """根据 business_id 更新或创建一个源记录。
        参数 `text` 已更名为 `text_content` 以保持命名一致性。
        """
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Generator[List[ContentItem], None, None]:  # 变更: TextItem -> ContentItem
        """以流式方式获取待翻译的内容批次。"""
        ...

    def save_translations(self, results: List[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    def garbage_collect(self, retention_days: int) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        ...

    def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...


class AsyncPersistenceHandler(Protocol):
    """异步持久化处理器的接口协议。
    签名与同步版本一一对应，但所有方法都是异步的 (`async def`)。
    """

    async def update_or_create_source(
        self, text_content: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        """根据 business_id 更新或创建一个源记录。"""
        ...

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[List[ContentItem], None]:  # 变更: TextItem -> ContentItem
        """以流式方式获取待翻译的内容批次。"""
        # 注意: Protocol 中的方法不应有实现，使用 '...' 表示抽象
        ...

    async def save_translations(self, results: List[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    async def garbage_collect(self, retention_days: int) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        ...

    async def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...
