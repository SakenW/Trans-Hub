"""
trans_hub/interfaces.py

本模块使用 typing.Protocol 定义了核心组件的接口（或称协议）。
这有助于实现依赖倒置，并使组件解耦、易于测试。
"""
from typing import Iterable, List, Optional, Protocol

from trans_hub.types import (
    SourceUpdateResult,
    TextItem,
    TranslationResult,
    TranslationStatus,
)

# ==============================================================================
#  持久化处理器接口 (Persistence Handler Interface)
# ==============================================================================

class PersistenceHandler(Protocol):
    """
    同步持久化处理器的接口协议。

    该接口定义了所有与数据库交互的同步操作。
    实现此接口的类负责处理所有数据的 CRUD (创建、读取、更新、删除) 操作，
    并确保写操作的原子性（事务性）。
    """

    def update_or_create_source(
        self, text: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        """
        根据 business_id 更新或创建一个源记录。

        此方法需要原子地执行以下逻辑：
        1. 查找 business_id。
        2. 如果存在但关联的 text 内容不同，则更新 th_sources 表指向新的 text_id。
        3. 如果 business_id 不存在，则创建新的 th_sources 记录。
        4. 如果 text 是新的，则在 th_texts 表中创建新记录。
        5. 更新 th_sources 中的 last_seen_at 时间戳。

        Args:
            text: 文本内容。
            business_id: 业务唯一标识符。
            context_hash: 与此次关联绑定的上下文哈希。

        Returns:
            一个 SourceUpdateResult 对象，包含 text_id 和一个布尔值，
            指示文本是否是新创建的。
        """
        ...

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Iterable[List[TextItem]]:
        """
        以流式方式获取待翻译的文本批次。

        此方法应在数据库层面原子地将返回的条目状态更新为 'TRANSLATING'，
        以防止多实例并发处理时出现重复工作。

        Args:
            lang_code: 目标语言代码。
            statuses: 要查询的翻译状态列表 (例如, [PENDING])。
            batch_size: 每个批次包含的条目数量。
            limit: 总共获取的最大条目数量，可选。

        Yields:
            一个 TextItem 列表，代表一个待处理的批次。
        """
        ...

    def save_translations(self, results: List[TranslationResult]) -> None:
        """
        将一批翻译结果保存到数据库中。

        此方法需要处理成功和失败的翻译结果，并相应地更新 th_translations 表中
        记录的状态、内容、引擎信息等。

        Args:
            results: 一个包含最终翻译结果的列表。
        """
        ...

    # ... 其他必要方法的签名将在这里添加，例如用于垃圾回收的方法 ...
    def garbage_collect(self, retention_days: int) -> dict:
        """
        执行垃圾回收，清理过时和孤立的数据。

        Args:
            retention_days: 数据保留天数。

        Returns:
            一个字典，包含清理结果的统计信息，如 {"deleted_sources": 10, "deleted_texts": 5}。
        """
        ...
        
    def close(self) -> None:
        """关闭数据库连接等资源。"""
        ...


class AsyncPersistenceHandler(Protocol):
    """
    异步持久化处理器的接口协议。

    此接口与同步版本的方法签名一一对应，但所有方法都是异步的 (async def)。
    """

    async def update_or_create_source(
        self, text: str, business_id: str, context_hash: Optional[str]
    ) -> SourceUpdateResult:
        ...

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: List[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> Iterable[List[TextItem]]: # 注意：异步生成器需要用 AsyncIterable
        ...

    async def save_translations(self, results: List[TranslationResult]) -> None:
        ...

    async def garbage_collect(self, retention_days: int) -> dict:
        ...

    async def close(self) -> None:
        ...