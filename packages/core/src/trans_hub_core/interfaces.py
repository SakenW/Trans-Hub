# packages/core/src/trans_hub_core/interfaces.py
"""
定义了 Trans-Hub 系统中所有基础设施和服务的抽象接口协议 (Protocols)。
这些接口是系统内部解耦的关键，高层模块（如 Application 层）应依赖于这些
抽象接口，而不是具体的实现类。
(v2.5.12 对齐版)
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .types import Comment, ContentItem, Event, TranslationHead


class PersistenceHandler(Protocol):
    """
    定义了数据库持久化处理器的纯异步接口协议。
    这是与主数据存储（Postgres/MySQL/SQLite）交互的唯一契约。
    """

    async def connect(self) -> None:
        """建立与数据库的连接。"""

    async def close(self) -> None:
        """关闭与数据库的连接。"""

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        source_lang: str,
        content_version: int,
    ) -> str:
        """根据 UIDA 幂等地创建或更新 th_content 记录，返回 content_id。"""

    async def get_content_id_by_uida(
        self, project_id: str, namespace: str, keys_sha256_bytes: bytes
    ) -> str | None:
        """通过 UIDA 的核心组件查找 content_id。"""

    async def get_or_create_translation_head(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
    ) -> tuple[str, int]:
        """获取或创建一个翻译头记录，返回 (head_id, current_revision_no)。"""

    async def create_new_translation_revision(
        self, *, head_id: str, project_id: str, content_id: str, **kwargs: Any
    ) -> str:
        """在 th.trans_rev 中创建一条新的修订，并更新 th.trans_head 的指针，返回 rev_id。"""

    async def find_tm_entry(
        self, *, project_id: str, namespace: str, reuse_sha: bytes, **kwargs: Any
    ) -> tuple[str, dict[str, Any]] | None:
        """在 TM 中查找可复用的翻译，返回 (tm_id, translated_json) 或 None。"""

    async def upsert_tm_entry(self, *, project_id: str, **kwargs: Any) -> str:
        """幂等地创建或更新 TM 条目，返回 tm_id。"""

    async def link_translation_to_tm(
        self, translation_rev_id: str, tm_id: str, project_id: str
    ) -> None:
        """在 th_tm_links 中创建一条追溯链接。"""

    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        """获取已发布的译文，返回 (rev_id, translated_payload_json) 或 None。"""

    async def publish_revision(self, revision_id: str) -> bool:
        """将一个 'reviewed' 状态的修订发布，返回是否成功。"""

    async def reject_revision(self, revision_id: str) -> bool:
        """将一个修订的状态标记为 'rejected'，返回是否成功。"""

    async def write_event(self, event: Event) -> None:
        """向 th_trans_events 写入一条事件记录。"""

    async def add_comment(self, comment: Comment) -> str:
        """向 th_trans_comments 添加一条评论，返回评论 ID。"""

    async def get_comments(self, head_id: str) -> list[Comment]:
        """获取指定 head_id 的所有评论。"""

    async def get_fallback_order(
        self, project_id: str, locale: str
    ) -> list[str] | None:
        """获取指定项目和语言的回退顺序。"""

    async def set_fallback_order(
        self, project_id: str, locale: str, fallback_order: list[str]
    ) -> None:
        """设置语言回退顺序。"""

    async def get_translation_head_by_uida(
        self, *, project_id: str, namespace: str, keys: dict[str, Any], target_lang: str, variant_key: str
    ) -> TranslationHead | None:
        """根据完整的 UIDA 和翻译维度获取一个翻译头记录的 DTO 对象。"""

    async def get_head_by_id(self, head_id: str) -> TranslationHead | None:
        """根据 Head ID 获取一个翻译头记录的 DTO 对象。"""

    async def get_head_by_revision(self, revision_id: str) -> TranslationHead | None:
        """根据 revision_id 查找其所属的 head。"""

    def stream_draft_translations(
        self, batch_size: int
    ) -> AsyncGenerator[list[ContentItem], None]:
        """流式获取待处理的 'draft' 状态翻译任务。"""
        ...


class CacheHandler(Protocol):
    """定义了分布式缓存处理器的接口。"""

    async def get(self, key: str) -> Any | None:
        """从缓存中获取一个值。"""

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """向缓存中设置一个值，并可选地设置过期时间（秒）。"""

    async def delete(self, key: str) -> None:
        """从缓存中删除一个键。"""


class LockProvider(Protocol):
    """定义了分布式锁提供者的接口。"""

    @asynccontextmanager
    def lock(self, key: str, timeout: float = 10.0) -> AsyncGenerator[None, None]:
        """
        一个异步上下文管理器，用于获取分布式锁。
        如果在 `timeout` 秒内无法获取锁，应抛出 `LockAcquisitionError`。
        """
        yield


class RateLimiter(Protocol):
    """定义了分布式速率限制器的接口。"""

    async def acquire(self, tokens_needed: int = 1) -> None:
        """异步获取指定数量的令牌，如果令牌不足则等待。"""


class QueueProducer(Protocol):
    """定义了任务队列生产者的接口。"""

    async def enqueue(self, queue_name: str, job: dict[str, Any]) -> None:
        """将一个任务放入指定的队列。"""


class StreamProducer(Protocol):
    """定义了事件流生产者的接口。"""

    async def publish(self, stream_name: str, event_data: dict[str, Any]) -> None:
        """向指定的事件流发布一条事件。"""