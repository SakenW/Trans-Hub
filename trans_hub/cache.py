# trans_hub/cache.py
"""本模块提供灵活的内存缓存机制，用于减少重复的翻译请求。"""

import asyncio
import hashlib
import json
from enum import Enum
from typing import Optional, Union

from cachetools import LRUCache, TTLCache

# 修复：导入 Field 用于添加约束
from pydantic import BaseModel, Field

from trans_hub.core.types import TranslationRequest


class CacheType(str, Enum):
    """定义了支持的缓存类型。"""

    TTL = "ttl"
    LRU = "lru"


class CacheConfig(BaseModel):
    """缓存配置模型。"""

    # 修复：为 maxsize 和 ttl 添加 gt=0 约束
    maxsize: int = Field(default=1000, gt=0)
    ttl: int = Field(default=3600, gt=0)
    cache_type: CacheType = CacheType.TTL


class TranslationCache:
    """一个用于管理翻译结果的、异步安全的内存缓存。"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache[str, str], TTLCache[str, str]]
        self._initialize_cache()
        # 修复：优化锁策略，仅在写入操作时加锁，提升并发读取性能
        self._write_lock = asyncio.Lock()

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
        # 修复：读取操作现在是无锁的，以提高并发性能。
        # cachetools 自身的 get 操作是线程安全的，对于 asyncio 来说，
        # 在没有 await 的情况下，单次操作是原子的，因此在这里是安全的。
        return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """异步、安全地将翻译结果存入缓存。"""
        key = self.generate_cache_key(request)
        async with self._write_lock:
            self.cache[key] = result

    async def clear_cache(self) -> None:
        """异步、安全地清空整个缓存。"""
        async with self._write_lock:
            self.cache.clear()
            self._initialize_cache()
