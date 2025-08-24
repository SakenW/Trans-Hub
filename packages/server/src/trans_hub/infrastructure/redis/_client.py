# packages/server/src/trans_hub/infrastructure/redis/_client.py
"""
集中管理 Redis 客户端的创建和生命周期。
"""

import redis.asyncio as aioredis
from trans_hub.config import TransHubConfig

_redis_client: aioredis.Redis | None = None


async def get_redis_client(config: TransHubConfig) -> aioredis.Redis:
    """获取一个单例的 Redis 异步客户端实例。"""
    global _redis_client
    if _redis_client is None:
        url = config.redis.url
        if not url:
            raise ValueError("Redis URL 未配置（请设置 TRANSHUB_REDIS__URL）")
        try:
            _redis_client = aioredis.from_url(url, decode_responses=True)
            # 测试连接是否可用
            await _redis_client.ping()
        except Exception as e:
            # 如果连接失败，抛出更详细的错误信息
            raise ValueError(f"无法连接到 Redis 服务器 {url}: {e}") from e
    return _redis_client


async def close_redis_client():
    """关闭全局 Redis 客户端连接。"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
