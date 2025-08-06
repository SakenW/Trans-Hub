# trans_hub/cache.py
"""本模块提供灵活的内存缓存机制，用于减少重复的翻译请求。"""

import asyncio
import hashlib
import json
from collections import defaultdict
from enum import Enum
from typing import Union

from cachetools import LRUCache, TTLCache
from pydantic import BaseModel, Field

from trans_hub.core.types import TranslationRequest


class CacheType(str, Enum):
    """定义了支持的缓存类型。"""

    TTL = "ttl"
    LRU = "lru"


class CacheConfig(BaseModel):
    """缓存配置模型。"""

    maxsize: int = Field(default=1000, gt=0)
    ttl: int = Field(default=3600, gt=0)
    cache_type: CacheType = CacheType.TTL


class TranslationCache:
    """一个用于管理翻译结果的、异步安全的内存缓存。"""

    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache[str, str], TTLCache[str, str]]
        self._initialize_cache()
        # 修复：实现按键的细粒度锁，以提升并发写入性能
        self._key_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 修复：为 clear_cache 和锁字典本身的管理提供一个全局锁
        self._global_lock = asyncio.Lock()

    def _initialize_cache(self) -> None:
        if self.config.cache_type is CacheType.TTL:
            self.cache = TTLCache(maxsize=self.config.maxsize, ttl=self.config.ttl)
        else:  # 默认为 LRU
            self.cache = LRUCache(maxsize=self.config.maxsize)

    def generate_cache_key(self, request: TranslationRequest) -> str:
        """为翻译请求生成一个唯一的、确定性的缓存键。"""
        payload_str = json.dumps(
            request.source_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        payload_hash = hashlib.sha256(payload_str).hexdigest()

        return "|".join(
            [
                payload_hash,
                request.source_lang or "auto",
                request.target_lang,
                request.context_hash,
                request.engine_name,
                request.engine_version,
            ]
        )

    async def get_cached_result(self, request: TranslationRequest) -> str | None:
        """从缓存中异步、安全地获取翻译结果。"""
        key = self.generate_cache_key(request)
        return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """异步、安全地将翻译结果存入缓存。"""
        key = self.generate_cache_key(request)
        # 获取特定于此键的锁，并写入缓存
        async with self._key_locks[key]:
            self.cache[key] = result

    async def clear_cache(self) -> None:
        """异步、安全地清空整个缓存。"""
        async with self._global_lock:
            self.cache.clear()
            self._key_locks.clear()
            self._initialize_cache()
