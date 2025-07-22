"""trans_hub/cache.py (v0.1)

提供灵活的缓存机制，减少重复翻译请求，提高系统性能。
支持TTL过期策略和LRU淘汰机制。
"""

import asyncio
from collections.abc import Awaitable
from functools import wraps
from typing import Callable, Optional, TypeVar, Union

from cachetools import LRUCache, TTLCache
from pydantic import BaseModel

from trans_hub.types import TranslationRequest

# 类型变量，用于泛型函数注解
T = TypeVar("T")


class CacheConfig(BaseModel):
    """缓存配置模型"""

    maxsize: int = 1000  # 缓存最大条目数
    ttl: int = 3600  # 缓存过期时间(秒)
    cache_type: str = "ttl"  # 缓存类型: ttl 或 lru


class TranslationCache:
    """翻译请求缓存管理器"""

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache: Union[LRUCache, TTLCache]
        self._initialize_cache()
        self._lock = asyncio.Lock()

    def _initialize_cache(self) -> None:
        """根据配置初始化缓存实例"""
        if self.config.cache_type == "ttl":
            self.cache = TTLCache(maxsize=self.config.maxsize, ttl=self.config.ttl)
        else:
            self.cache = LRUCache(maxsize=self.config.maxsize)

    def generate_cache_key(self, request: TranslationRequest) -> str:
        """生成翻译请求的唯一缓存键"""
        # 基于请求的所有关键参数生成缓存键
        return "|".join(
            [
                request.source_text,
                request.source_lang or "auto",
                request.target_lang,
                str(request.context_hash) if request.context_hash else "",
            ]
        )

    async def get_cached_result(self, request: TranslationRequest) -> Optional[str]:
        """从缓存获取翻译结果"""
        key = self.generate_cache_key(request)
        async with self._lock:
            return self.cache.get(key)

    async def cache_translation_result(
        self, request: TranslationRequest, result: str
    ) -> None:
        """缓存翻译结果"""
        key = self.generate_cache_key(request)
        async with self._lock:
            self.cache[key] = result

    def clear_cache(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self._initialize_cache()  # 重新初始化以保持配置


# 缓存装饰器 - 用于同步函数
def cache_translation(config: Optional[CacheConfig] = None):
    """装饰器：缓存翻译函数的结果"""
    cache = TranslationCache(config)

    def decorator(
        func: Callable[[TranslationRequest], str],
    ) -> Callable[[TranslationRequest], str]:
        @wraps(func)
        def wrapper(request: TranslationRequest) -> str:
            # 尝试从缓存获取
            cached_result = asyncio.run(cache.get_cached_result(request))
            if cached_result:
                return cached_result

            # 调用原始函数
            result = func(request)

            # 缓存结果
            asyncio.run(cache.cache_translation_result(request, result))
            return result

        return wrapper

    return decorator


# 异步缓存装饰器 - 用于异步函数
def async_cache_translation(config: Optional[CacheConfig] = None):
    """装饰器：异步缓存翻译函数的结果"""
    cache = TranslationCache(config)

    def decorator(
        func: Callable[[TranslationRequest], Awaitable[str]],
    ) -> Callable[[TranslationRequest], Awaitable[str]]:
        @wraps(func)
        async def wrapper(request: TranslationRequest) -> str:
            # 尝试从缓存获取
            cached_result = await cache.get_cached_result(request)
            if cached_result:
                return cached_result

            # 调用原始函数
            result = await func(request)

            # 缓存结果
            await cache.cache_translation_result(request, result)
            return result

        return wrapper

    return decorator
