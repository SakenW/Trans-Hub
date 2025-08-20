# packages/core/src/trans_hub_core/interfaces.py
"""
定义了 Trans-Hub 系统中所有基础设施和服务的抽象接口协议 (Protocols)。
这些接口是系统内部解耦的关键，高层模块（如 Application 层）应依赖于这些
抽象接口，而不是具体的实现类。
(v3.1.0 UoW 模式对齐版)
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    # [移除] 不再需要导入 TranslationHead, Comment, Event, ContentItem
    pass


class CacheHandler(Protocol):
    """定义了分布式缓存处理器的接口。"""

    async def get(self, key: str) -> Any | None:
        """从缓存中获取一个值。"""
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """向缓存中设置一个值，并可选地设置过期时间（秒）。"""
        ...

    async def delete(self, key: str) -> None:
        """从缓存中删除一个键。"""
        ...


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
        ...


class QueueProducer(Protocol):
    """定义了任务队列生产者的接口。"""

    async def enqueue(self, queue_name: str, job: dict[str, Any]) -> None:
        """将一个任务放入指定的队列。"""
        ...


class StreamProducer(Protocol):
    """定义了事件流生产者的接口。"""

    async def publish(self, stream_name: str, event_data: dict[str, Any]) -> None:
        """向指定的事件流发布一条事件。"""
        ...