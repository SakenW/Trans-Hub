# packages/server/src/trans_hub/containers/cache.py
"""
[DI 重构] 缓存与分布式控制层容器。

负责管理 Redis 客户端连接和基于其上的服务（如缓存处理器）。
"""

import redis.asyncio as aioredis
from dependency_injector import containers, providers
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.redis._client import get_redis_client
from trans_hub.infrastructure.redis.cache import RedisCacheHandler
from trans_hub_core.interfaces import CacheHandler


class CacheContainer(containers.DeclarativeContainer):
    """缓存层相关服务的容器。"""

    config = providers.Dependency(instance_of=TransHubConfig)

    # Redis 客户端是一个异步资源，仅在配置了 URL 时才初始化
    redis_client: providers.Resource[aioredis.Redis] = providers.Resource(
        get_redis_client,
        config=config,
    )

    # 缓存处理器是一个单例，依赖于 Redis 客户端
    cache_handler: providers.Singleton[CacheHandler] = providers.Singleton(
        RedisCacheHandler,
        client=redis_client,
        key_prefix=config.provided.redis.key_prefix,
    )
