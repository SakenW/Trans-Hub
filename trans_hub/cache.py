# trans_hub/cache.py
"""本模块提供灵活的内存缓存机制，用于减少重复的翻译请求。"""

import asyncio
import hashlib
import json
from enum import Enum
from typing import Optional, Union

from cachetools import LRUCache, TTLCache
from pydantic import BaseModel

from trans_hub.core.types import TranslationRequest


# v3.10 修复：使用枚举来约束缓存类型，增强配置的健壮性
class CacheType(str, Enum):
    """定义了支持的缓存类型。"""

    TTL = "ttl"
    LRU = "lru"


class CacheConfig(BaseModel):
    """缓存配置模型。"""

    maxsize: int = 1000
    ttl: int = 3600
    cache_type: CacheType = CacheType.TTL


class TranslationCache:
    """一个用于管理翻译结果的、异步安全的内存缓存。"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache[str, str], TTLCache[str, str]]
        self._initialize_cache()
        self._lock = asyncio.Lock()

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
