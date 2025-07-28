# trans_hub/cache.py
"""
本模块提供灵活的内存缓存机制，用于减少重复的翻译请求。

它支持基于 TTL (Time-To-Live) 的过期策略和基于 LRU (Least Recently Used)
的淘汰机制，以优化性能和内存使用。
"""

import asyncio
from typing import Optional, Union

from cachetools import LRUCache, TTLCache
from pydantic import BaseModel

from trans_hub.types import TranslationRequest


class CacheConfig(BaseModel):
    """缓存配置模型。"""

    maxsize: int = 1000
    ttl: int = 3600
    cache_type: str = "ttl"


class TranslationCache:
    """
    一个用于管理翻译结果的、异步安全的内存缓存。

    它封装了 `cachetools` 库，并使用 `asyncio.Lock` 来确保在异步环境中的线程安全。
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        """
        初始化翻译缓存。

        参数:
            config: 缓存配置对象。如果未提供，则使用默认配置。
        """
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache, TTLCache]
        self._initialize_cache()
        self._lock = asyncio.Lock()

    def _initialize_cache(self) -> None:
        """[私有] 根据配置初始化 `cachetools` 缓存实例。"""
        if self.config.cache_type == "ttl":
            self.cache = TTLCache(maxsize=self.config.maxsize, ttl=self.config.ttl)
        else:
            self.cache = LRUCache(maxsize=self.config.maxsize)

    def generate_cache_key(self, request: TranslationRequest) -> str:
        """为翻译请求生成一个唯一的、确定性的缓存键。"""
        return "|".join(
            [
                request.source_text,
                request.source_lang or "auto",
                request.target_lang,
                request.context_hash,
            ]
        )

    async def get_cached_result(self, request: TranslationRequest) -> Optional[str]:
        """从缓存中异步、安全地获取翻译结果。"""
        key = self.generate_cache_key(request)
        async with self._lock:
            return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """异步、安全地将翻译结果存入缓存。"""
        key = self.generate_cache_key(request)
        async with self._lock:
            self.cache[key] = result

    async def clear_cache(self) -> None:
        """异步、安全地清空整个缓存。"""
        async with self._lock:
            self.cache.clear()
            self._initialize_cache()
