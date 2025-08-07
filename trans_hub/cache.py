# trans_hub/cache.py
"""本模块提供灵活的内存缓存机制，用于减少重复的翻译请求。"""

import asyncio
import hashlib
import json
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
    # 新增：可配置的锁池大小
    lock_pool_size: int = Field(
        default=1024, gt=0, description="用于并发写入的锁池大小"
    )


class TranslationCache:
    """一个用于管理翻译结果的、异步安全的内存缓存。"""

    def __init__(self, config: CacheConfig | None = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache[str, str], TTLCache[str, str]]

        # --- 核心修复 ---
        # 从 defaultdict 修改为固定大小的锁池（分段锁）
        self._lock_pool_size = self.config.lock_pool_size
        self._key_locks: list[asyncio.Lock] = [
            asyncio.Lock() for _ in range(self._lock_pool_size)
        ]

        self._initialize_cache()
        # 全局锁仍然用于管理 clear_cache 等全局操作
        self._global_lock = asyncio.Lock()

    def _initialize_cache(self) -> None:
        if self.config.cache_type is CacheType.TTL:
            self.cache = TTLCache(maxsize=self.config.maxsize, ttl=self.config.ttl)
        else:
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
        # 读取操作通常是线程安全的，但在高并发 TTL 场景下加锁更稳妥
        lock = self._key_locks[hash(key) % self._lock_pool_size]
        async with lock:
            return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """异步、安全地将翻译结果存入缓存。"""
        key = self.generate_cache_key(request)
        # --- 核心修复 ---
        # 通过哈希值选择一个锁，而不是为每个键创建一个新锁
        lock = self._key_locks[hash(key) % self._lock_pool_size]
        async with lock:
            self.cache[key] = result

    async def clear_cache(self) -> None:
        """异步、安全地清空整个缓存。"""
        async with self._global_lock:
            # 重新创建锁池以防万一，尽管通常不需要
            self._key_locks = [asyncio.Lock() for _ in range(self._lock_pool_size)]
            self._initialize_cache()
