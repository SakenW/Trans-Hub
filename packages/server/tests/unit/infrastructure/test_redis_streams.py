# tests/unit/infrastructure/test_redis_streams.py
"""
RedisStreamProducer 的单元测试。

测试新的 JSON 序列化功能和错误处理机制。
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from trans_hub.infrastructure.redis.streams import RedisStreamProducer


class TestRedisStreamProducer:
    """RedisStreamProducer 的测试用例。"""

    @pytest.fixture
    def mock_redis_client(self):
        """创建模拟的 Redis 客户端。"""
        client = Mock()
        client.xadd = AsyncMock()
        return client

    @pytest.fixture
    def producer(self, mock_redis_client):
        """创建 RedisStreamProducer 实例。"""
        return RedisStreamProducer(mock_redis_client)

    @pytest.mark.asyncio
    async def test_publish_simple_event(self, producer, mock_redis_client):
        """测试发布简单事件。"""
        stream_name = "test_stream"
        event_data = {
            "type": "test_event",
            "message": "Hello, World!",
            "count": 42
        }

        await producer.publish(stream_name, event_data)

        # 验证 xadd 被调用
        mock_redis_client.xadd.assert_called_once()
        call_args = mock_redis_client.xadd.call_args
        
        # 验证 stream 名称
        assert call_args[0][0] == stream_name
        
        # 验证事件数据格式
        flat_event_data = call_args[0][1]
        assert "payload" in flat_event_data
        
        # 验证 JSON 序列化
        parsed_data = json.loads(flat_event_data["payload"])
        assert parsed_data == event_data

    @pytest.mark.asyncio
    async def test_publish_nested_event(self, producer, mock_redis_client):
        """测试发布包含嵌套结构的事件。"""
        stream_name = "test_stream"
        event_data = {
            "type": "complex_event",
            "metadata": {
                "source": "test",
                "timestamp": "2024-01-15T10:30:00Z",
                "tags": ["tag1", "tag2"]
            },
            "metrics": {
                "duration_ms": 1500,
                "success": True
            }
        }

        await producer.publish(stream_name, event_data)

        # 验证调用
        mock_redis_client.xadd.assert_called_once()
        call_args = mock_redis_client.xadd.call_args
        
        # 验证嵌套结构被正确序列化
        flat_event_data = call_args[0][1]
        parsed_data = json.loads(flat_event_data["payload"])
        assert parsed_data == event_data
        assert parsed_data["metadata"]["tags"] == ["tag1", "tag2"]
        assert parsed_data["metrics"]["success"] is True

    @pytest.mark.asyncio
    async def test_publish_with_non_serializable_data(self, producer, mock_redis_client):
        """测试发布不可序列化的数据时的错误处理。"""
        stream_name = "test_stream"
        
        # 创建不可序列化的对象
        class NonSerializable:
            pass
        
        event_data = {
            "type": "invalid_event",
            "data": NonSerializable()  # 不可序列化
        }

        # 验证抛出异常
        with pytest.raises((TypeError, ValueError)):
            await producer.publish(stream_name, event_data)
        
        # 验证 xadd 没有被调用
        mock_redis_client.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_with_redis_error(self, producer, mock_redis_client):
        """测试 Redis 操作失败时的错误处理。"""
        stream_name = "test_stream"
        event_data = {"type": "test_event"}
        
        # 模拟 Redis 错误
        mock_redis_client.xadd.side_effect = Exception("Redis connection failed")

        # 验证异常被重新抛出
        with pytest.raises(Exception, match="Redis connection failed"):
            await producer.publish(stream_name, event_data)

    @pytest.mark.asyncio
    async def test_publish_with_unicode_content(self, producer, mock_redis_client):
        """测试发布包含 Unicode 字符的事件。"""
        stream_name = "test_stream"
        event_data = {
            "type": "unicode_event",
            "message": "你好，世界！🌍",
            "emoji": "🚀✨🎉",
            "special_chars": "àáâãäåæçèéêë"
        }

        await producer.publish(stream_name, event_data)

        # 验证调用
        mock_redis_client.xadd.assert_called_once()
        call_args = mock_redis_client.xadd.call_args
        
        # 验证 Unicode 字符被正确处理
        flat_event_data = call_args[0][1]
        parsed_data = json.loads(flat_event_data["payload"])
        assert parsed_data == event_data
        assert parsed_data["message"] == "你好，世界！🌍"
        assert parsed_data["emoji"] == "🚀✨🎉"

    @pytest.mark.asyncio
    async def test_publish_empty_event(self, producer, mock_redis_client):
        """测试发布空事件。"""
        stream_name = "test_stream"
        event_data = {}

        await producer.publish(stream_name, event_data)

        # 验证调用
        mock_redis_client.xadd.assert_called_once()
        call_args = mock_redis_client.xadd.call_args
        
        # 验证空事件被正确处理
        flat_event_data = call_args[0][1]
        parsed_data = json.loads(flat_event_data["payload"])
        assert parsed_data == {}

    @pytest.mark.asyncio
    async def test_json_serialization_options(self, producer, mock_redis_client):
        """测试 JSON 序列化选项。"""
        stream_name = "test_stream"
        event_data = {
            "chinese": "中文测试",
            "japanese": "日本語テスト",
            "korean": "한국어 테스트"
        }

        await producer.publish(stream_name, event_data)

        # 验证调用
        call_args = mock_redis_client.xadd.call_args
        flat_event_data = call_args[0][1]
        
        # 验证 ensure_ascii=False 选项生效
        # JSON 字符串应该包含原始的非 ASCII 字符，而不是转义序列
        payload_str = flat_event_data["payload"]
        assert "中文测试" in payload_str
        assert "日本語テスト" in payload_str
        assert "한국어 테스트" in payload_str
        
        # 验证可以正确解析
        parsed_data = json.loads(payload_str)
        assert parsed_data == event_data