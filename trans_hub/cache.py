# trans_hub/cache.py (修正后)
"""提供灵活的缓存机制，减少重复翻译请求，提高系统性能。
支持TTL过期策略和LRU淘汰机制。.
"""

import asyncio
from collections.abc import Awaitable
from functools import wraps
from typing import Callable, Optional, Union

from cachetools import LRUCache, TTLCache
from pydantic import BaseModel

from trans_hub.types import TranslationRequest


class CacheConfig(BaseModel):
    """缓存配置模型."""

    maxsize: int = 1000
    ttl: int = 3600
    cache_type: str = "ttl"


class TranslationCache:
    """翻译请求的异步安全缓存管理器."""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache, TTLCache]
        self._initialize_cache()
        self._lock = asyncio.Lock()

    def _initialize_cache(self) -> None:
        """根据配置初始化缓存实例."""
        if self.config.cache_type == "ttl":
            self.cache = TTLCache(maxsize=self.config.maxsize, ttl=self.config.ttl)
        else:
            self.cache = LRUCache(maxsize=self.config.maxsize)

    def generate_cache_key(self, request: TranslationRequest) -> str:
        """为翻译请求生成唯一的缓存键."""
        return "|".join(
            [
                request.source_text,
                request.source_lang or "auto",
                request.target_lang,
                request.context_hash,
            ]
        )

    async def get_cached_result(self, request: TranslationRequest) -> Optional[str]:
        """从缓存中异步获取翻译结果."""
        key = self.generate_cache_key(request)
        async with self._lock:
            return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """异步地将翻译结果存入缓存."""
        key = self.generate_cache_key(request)
        async with self._lock:
            self.cache[key] = result

    async def clear_cache(self) -> None:
        """异步地清空缓存."""
        async with self._lock:
            self.cache.clear()
            self._initialize_cache()


# (已移除) 同步的 cache_translation 装饰器，因为它使用了 asyncio.run()，与纯异步架构不兼容。


# 异步缓存装饰器 (保留供未来使用)
def async_cache_translation(config: Optional[CacheConfig] = None):
    """装饰器：为异步函数的结果提供缓存。."""
    cache = TranslationCache(config)

    def decorator(
        func: Callable[[TranslationRequest], Awaitable[str]],
    ) -> Callable[[TranslationRequest], Awaitable[str]]:
        @wraps(func)
        async def wrapper(request: TranslationRequest) -> str:
            cached_result = await cache.get_cached_result(request)
            if cached_result is not None:
                return cached_result

            result = await func(request)
            await cache.cache_translation_result(request, result)
            return result

        return wrapper

    return decorator
