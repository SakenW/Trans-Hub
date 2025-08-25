# packages/server/tests/unit/di/test_container_no_redis.py
"""
测试 DI 容器在无 Redis 配置下的行为。
"""

from trans_hub.config import TransHubConfig
from trans_hub.di.container import AppContainer


def test_create_stream_producer_function_with_no_redis():
    """测试 _create_stream_producer 函数在无 Redis URL 时返回 None。"""
    
    # 创建一个没有 Redis URL 的配置
    config = TransHubConfig(
        database={
            "url": "sqlite+aiosqlite:///test.db",
            "default_schema": "public",
        },
        redis={
            "url": "",  # 空的 Redis URL
            "key_prefix": "test:",
        },
        active_engine="debug",
    )
    
    # 直接测试 _create_stream_producer 函数
    result = AppContainer._create_stream_producer(config, None)
    assert result is None


def test_create_stream_producer_function_with_redis():
    """测试 _create_stream_producer 函数在有 Redis URL 时尝试创建实例。"""
    from unittest.mock import Mock
    
    # 创建一个有 Redis URL 的配置
    config = TransHubConfig(
        database={
            "url": "sqlite+aiosqlite:///test.db",
            "default_schema": "public",
        },
        redis={
            "url": "redis://localhost:6379",
            "key_prefix": "test:",
        },
        active_engine="debug",
    )
    
    # 使用 mock Redis 客户端
    mock_redis_client = Mock()
    
    # 测试 _create_stream_producer 函数
    result = AppContainer._create_stream_producer(config, mock_redis_client)
    assert result is not None
    # 验证返回的是 RedisStreamProducer 实例
    from trans_hub.infrastructure.redis.streams import RedisStreamProducer
    assert isinstance(result, RedisStreamProducer)


def test_translation_processor_with_none_stream_producer():
    """测试 TranslationProcessor 能够接受 None 的 stream_producer。"""
    from trans_hub.application.processors import TranslationProcessor
    
    # 直接创建 TranslationProcessor，传入 None 作为 stream_producer
    processor = TranslationProcessor(
        stream_producer=None,
        event_stream_name="test_events"
    )
    
    assert processor is not None
    assert processor._stream_producer is None