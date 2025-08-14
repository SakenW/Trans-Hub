# packages/server/src/trans_hub/infrastructure/redis/streams.py
"""
使用 Redis Streams 实现 `StreamProducer` 接口。

Redis Streams 是一种功能强大的数据结构，非常适合用作持久化的、
可消费的事件总线。
"""

from typing import Any

import redis.asyncio as aioredis
import structlog

from trans_hub_core.interfaces import StreamProducer

logger = structlog.get_logger(__name__)


class RedisStreamProducer(StreamProducer):
    """
    基于 Redis Streams 的事件流生产者实现。
    """

    def __init__(self, client: aioredis.Redis):
        """
        初始化生产者。

        Args:
            client: 一个配置好的 Redis 异步客户端实例。
        """
        self._client = client

    async def publish(self, stream_name: str, event_data: dict[str, Any]) -> None:
        """
        向指定的 Redis Stream 发布一条事件。

        Args:
            stream_name: Stream 的键名。
            event_data: 要发布的事件内容（必须是扁平的 string-to-string 字典）。
        """
        try:
            # Redis Streams 的字段和值都必须是字符串。
            # 我们将事件数据转换为适合的格式。
            # 注意：真实的实现可能需要一个更健壮的序列化器（如 JSON）。
            flat_event_data = {
                str(k): str(v) for k, v in event_data.items() if v is not None
            }

            # 使用 XADD 命令将事件添加到 Stream 的末尾
            await self._client.xadd(stream_name, flat_event_data)

            logger.debug("事件已成功发布到 Redis Stream", stream=stream_name)

        except Exception:
            logger.error(
                "发布事件到 Redis Stream 失败",
                stream=stream_name,
                exc_info=True,
            )
            # 在生产环境中，这里可能需要一个回退机制或告警
