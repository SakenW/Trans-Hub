# packages/server/src/trans_hub/infrastructure/redis/cache.py
"""
使用 Redis 实现 `CacheHandler` 接口。
"""

import json
from typing import Any

import redis.asyncio as aioredis

from trans_hub_core.interfaces import CacheHandler


class RedisCacheHandler(CacheHandler):
    """基于 Redis 的分布式缓存实现。"""

    def __init__(self, client: aioredis.Redis, key_prefix: str = "trans-hub:cache:"):
        self._client = client
        self._prefix = key_prefix

    async def get(self, key: str) -> Any | None:
        """从 Redis 获取缓存值并反序列化。"""
        try:
            raw_value = await self._client.get(self._prefix + key)
            if raw_value is None:
                return None
            return json.loads(raw_value)
        except (json.JSONDecodeError, Exception):
            # 如果反序列化失败，返回 None
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """序列化值并写入 Redis，支持 TTL。"""
        try:
            serialized_value = json.dumps(value)
            await self._client.set(self._prefix + key, serialized_value, ex=ttl)
        except (TypeError, Exception):
            # 如果序列化失败，忽略此次缓存操作
            pass

    async def delete(self, key: str) -> None:
        """从 Redis 删除指定键。"""
        await self._client.delete(self._prefix + key)
