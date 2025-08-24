# packages/server/src/trans_hub/infrastructure/cache/memory.py
"""
内存缓存实现，用于测试环境或当 Redis 不可用时的备用方案。
"""

from typing import Any

from trans_hub_core.interfaces import CacheHandler


class MemoryCacheHandler(CacheHandler):
    """基于内存的缓存实现，用于测试环境。"""

    def __init__(self, key_prefix: str = "trans-hub:cache:"):
        self._cache: dict[str, Any] = {}
        self._prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """生成带前缀的缓存键。"""
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> Any | None:
        """从内存缓存中获取值。"""
        full_key = self._make_key(key)
        return self._cache.get(full_key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """设置缓存值到内存中。注意：TTL 在内存实现中被忽略。"""
        full_key = self._make_key(key)
        self._cache[full_key] = value

    async def delete(self, key: str) -> None:
        """从内存缓存中删除值。"""
        full_key = self._make_key(key)
        self._cache.pop(full_key, None)

    def clear(self) -> None:
        """清空所有缓存。"""
        self._cache.clear()