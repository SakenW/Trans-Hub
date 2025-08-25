# packages/server/src/trans_hub/infrastructure/redis/cache.py
"""
使用 Redis 实现 `CacheHandler` 接口。
"""

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from trans_hub_core.interfaces import CacheHandler


class RedisCacheHandler(CacheHandler):
    """基于 Redis 的分布式缓存实现。"""

    def __init__(self, client: aioredis.Redis, key_prefix: str = "trans-hub:cache:"):
        self._client = client
        self._prefix = key_prefix
        self._logger = structlog.get_logger(__name__)

    async def get(self, key: str) -> Any | None:
        """从 Redis 获取缓存值并反序列化。"""
        try:
            raw_value = await self._client.get(self._prefix + key)
            if raw_value is None:
                return None
            return json.loads(raw_value)
        except json.JSONDecodeError as e:
            # 反序列化失败，记录警告并返回 None
            self._logger.warning(
                "缓存值反序列化失败",
                key=key,
                raw_value=raw_value,
                error=str(e)
            )
            return None
        except aioredis.RedisError as e:
            # Redis 连接或操作错误，记录错误并返回 None
            self._logger.error(
                "Redis 操作失败",
                operation="get",
                key=key,
                error=str(e)
            )
            return None
        except Exception as e:
            # 其他未预期的异常，记录错误并重新抛出
            self._logger.error(
                "缓存获取时发生未预期异常",
                key=key,
                error=str(e),
                exc_info=True
            )
            raise

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """序列化值并写入 Redis，支持 TTL。"""
        try:
            serialized_value = json.dumps(value)
        except TypeError as e:
            # 序列化失败，记录警告并跳过写入
            self._logger.warning(
                "缓存值序列化失败，跳过写入",
                key=key,
                value_type=type(value).__name__,
                error=str(e)
            )
            return
        
        try:
            await self._client.set(self._prefix + key, serialized_value, ex=ttl)
        except aioredis.RedisError as e:
            # Redis 连接或操作错误，记录错误并重新抛出
            self._logger.error(
                "Redis 写入操作失败",
                operation="set",
                key=key,
                ttl=ttl,
                error=str(e)
            )
            raise

    async def delete(self, key: str) -> None:
        """从 Redis 删除指定键。"""
        await self._client.delete(self._prefix + key)
