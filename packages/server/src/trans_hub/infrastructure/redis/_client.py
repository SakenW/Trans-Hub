# packages/server/src/trans_hub/infrastructure/redis/_client.py
"""
集中管理 Redis 客户端的创建和生命周期。
"""
import redis.asyncio as aioredis
from trans_hub.config import TransHubConfig

_redis_client: aioredis.Redis | None = None

async def get_redis_client(config: TransHubConfig) -> aioredis.Redis:
    """
    获取一个单例的 Redis 异步客户端实例。
    """
    global _redis_client
    if _redis_client is None:
        if not config.redis_url:
            raise ValueError("Redis URL 未配置 (TH_REDIS_URL)")
        _redis_client = aioredis.from_url(config.redis_url, decode_responses=True)
    return _redis_client

async def close_redis_client():
    """关闭全局 Redis 客户端连接。"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None