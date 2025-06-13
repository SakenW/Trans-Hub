"""trans_hub/interfaces.py (v0.2)

本模块使用 typing.Protocol 定义了核心组件的接口（或称协议）。
此版本已根据最终版文档的术语和数据传输对象（DTOs）进行更新，
并包含了对事务管理和垃圾回收参数的协议扩展。
"""

from contextlib import (
    AbstractContextManager,
)
from typing import Any, AsyncGenerator, Generator, List, Optional, Protocol

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
    ) -> Generator[List[ContentItem], None, None]:
        """以流式方式获取待翻译的内容批次。"""
        ...

    def save_translations(self, results: List[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。
        Args:
            retention_days: 数据保留天数。
            dry_run: 如果为 True，则只报告将要删除的数据，不实际执行删除。
        Returns:
            包含垃圾回收结果的字典。
        """
        ...

    def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...

    def transaction(self) -> AbstractContextManager[Any]:
        """提供一个同步数据库事务上下文管理器。
        可以与 `with` 语句一起使用，例如 `with handler.transaction() as db_session:`。
        实际实现应根据其数据库访问方式返回合适的上下文管理器（例如，一个数据库连接或会话）。
        Returns:
            一个上下文管理器。
        """
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
    ) -> AsyncGenerator[List[ContentItem], None]:
        """以流式方式获取待翻译的内容批次。"""
        ...

    async def save_translations(self, results: List[TranslationResult]) -> None:
        """将一批翻译结果保存到数据库中。"""
        ...

    async def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict:
        """执行垃圾回收，清理过时和孤立的数据。"""
        ...

    async def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...

    async def transaction(
        self,
    ) -> AbstractContextManager[
        Any
    ]:  # 注意：async context managers 通常使用 AsyncContextManager
        """提供一个异步数据库事务上下文管理器。
        可以与 `async with` 语句一起使用。
        Returns:
            一个异步上下文管理器。
        """
        # 理论上应该使用 `typing.AsyncContextManager` 但为了 Mypy 兼容性，
        # 且考虑到 `AbstractContextManager` 是 `typing.ContextManager` 的超类，
        # 在某些情况下 Mypy 可能更宽松。若仍报错，可以尝试 `typing.AsyncContextManager`。
        ...
