#!/usr/bin/env python3
# packages/server/examples/redis_stream_consumer.py
"""
Redis Stream 消费端示例。

演示如何正确消费和解析 RedisStreamProducer 发布的事件。
事件数据使用 JSON 序列化格式存储在 'payload' 字段中。

运行前请确保：
1. Redis 服务器正在运行
2. 已安装必要的依赖：poetry install
3. 设置环境变量 REDIS_URL（可选，默认使用 redis://localhost:6379/0）
"""

import asyncio
import json
import os
from typing import Any, Dict

import redis.asyncio as aioredis
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class RedisStreamConsumer:
    """
    Redis Stream 消费者示例实现。
    
    演示如何正确解析 RedisStreamProducer 发布的 JSON 序列化事件。
    """

    def __init__(self, redis_client: aioredis.Redis, consumer_group: str = "example_group"):
        self.redis_client = redis_client
        self.consumer_group = consumer_group
        self.consumer_name = "example_consumer"

    async def create_consumer_group(self, stream_name: str) -> None:
        """
        创建消费者组（如果不存在）。
        
        Args:
            stream_name: Stream 名称
        """
        try:
            await self.redis_client.xgroup_create(
                stream_name, self.consumer_group, id="0", mkstream=True
            )
            logger.info("消费者组创建成功", stream=stream_name, group=self.consumer_group)
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug("消费者组已存在", stream=stream_name, group=self.consumer_group)
            else:
                logger.error("创建消费者组失败", error=str(e), exc_info=True)
                raise

    def parse_event_data(self, raw_data: Dict[bytes, bytes]) -> Dict[str, Any]:
        """
        解析从 Redis Stream 读取的原始事件数据。
        
        Args:
            raw_data: Redis Stream 返回的原始数据（bytes 格式）
            
        Returns:
            解析后的事件数据字典
            
        Raises:
            ValueError: 当事件数据格式不正确时
        """
        try:
            # Redis Stream 返回的数据是 bytes 格式，需要先解码
            if b'payload' not in raw_data:
                raise ValueError("事件数据中缺少 'payload' 字段")
            
            # 解码 payload 字段
            payload_str = raw_data[b'payload'].decode('utf-8')
            
            # 解析 JSON 数据
            event_data = json.loads(payload_str)
            
            logger.debug("事件数据解析成功", event_data_keys=list(event_data.keys()))
            return event_data
            
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败", error=str(e), payload=raw_data.get(b'payload', b'').decode('utf-8', errors='replace'))
            raise ValueError(f"无效的 JSON 格式: {e}")
        except UnicodeDecodeError as e:
            logger.error("UTF-8 解码失败", error=str(e))
            raise ValueError(f"无效的 UTF-8 编码: {e}")
        except Exception as e:
            logger.error("解析事件数据时发生未知错误", error=str(e), exc_info=True)
            raise ValueError(f"解析事件数据失败: {e}")

    async def consume_events(self, stream_name: str, count: int = 10, block: int = 1000) -> None:
        """
        消费指定 Stream 中的事件。
        
        Args:
            stream_name: Stream 名称
            count: 每次读取的最大事件数量
            block: 阻塞等待时间（毫秒），0 表示不阻塞
        """
        await self.create_consumer_group(stream_name)
        
        logger.info(
            "开始消费事件",
            stream=stream_name,
            group=self.consumer_group,
            consumer=self.consumer_name
        )
        
        try:
            while True:
                # 使用 XREADGROUP 读取事件
                response = await self.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {stream_name: ">"},
                    count=count,
                    block=block
                )
                
                if not response:
                    logger.debug("未读取到新事件，继续等待...")
                    continue
                
                # 处理读取到的事件
                for stream, messages in response:
                    for message_id, raw_data in messages:
                        try:
                            # 解析事件数据
                            event_data = self.parse_event_data(raw_data)
                            
                            # 处理事件（这里只是打印，实际应用中应该调用具体的业务逻辑）
                            await self.process_event(message_id.decode(), event_data)
                            
                            # 确认消息已处理
                            await self.redis_client.xack(stream_name, self.consumer_group, message_id)
                            
                        except Exception as e:
                            logger.error(
                                "处理事件失败",
                                message_id=message_id.decode(),
                                error=str(e),
                                exc_info=True
                            )
                            # 在实际应用中，可能需要将失败的消息发送到死信队列
                            
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止消费事件")
        except Exception as e:
            logger.error("消费事件时发生错误", error=str(e), exc_info=True)
            raise

    async def process_event(self, message_id: str, event_data: Dict[str, Any]) -> None:
        """
        处理单个事件的业务逻辑。
        
        Args:
            message_id: 消息 ID
            event_data: 解析后的事件数据
        """
        logger.info(
            "处理事件",
            message_id=message_id,
            event_type=event_data.get('type', 'unknown'),
            event_data=event_data
        )
        
        # 这里添加具体的业务逻辑
        # 例如：
        # if event_data.get('type') == 'translation_completed':
        #     await self.handle_translation_completed(event_data)
        # elif event_data.get('type') == 'task_failed':
        #     await self.handle_task_failed(event_data)


async def main():
    """
    示例主函数。
    """
    # 从环境变量获取 Redis URL，默认使用本地 Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # 创建 Redis 客户端
    redis_client = aioredis.from_url(redis_url)
    
    try:
        # 测试连接
        await redis_client.ping()
        logger.info("Redis 连接成功", url=redis_url)
        
        # 创建消费者
        consumer = RedisStreamConsumer(redis_client)
        
        # 开始消费事件（这里使用示例 Stream 名称）
        stream_name = "translation_events"
        await consumer.consume_events(stream_name)
        
    except Exception as e:
        logger.error("运行消费者时发生错误", error=str(e), exc_info=True)
    finally:
        await redis_client.close()
        logger.info("Redis 连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())