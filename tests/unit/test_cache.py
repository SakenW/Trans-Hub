# tests/unit/test_cache.py
"""
针对 `trans_hub.cache` 模块的单元测试。

本测试文件验证了缓存的基本功能（设置、获取、TTL过期）以及
缓存键生成的正确性（基于哈希、稳定性）。
"""

import pytest
from cachetools import TTLCache
from pytest_mock import MockerFixture

from trans_hub.cache import CacheConfig, CacheType, TranslationCache
from trans_hub.core.types import TranslationRequest


@pytest.fixture
def sample_request() -> TranslationRequest:
    """提供一个可复用的翻译请求对象。"""
    # 修复：添加 engine_name 和 engine_version
    return TranslationRequest(
        source_payload={"text": "Hello"},
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
        engine_name="debug",
        engine_version="1.0",
    )


@pytest.fixture
def another_request() -> TranslationRequest:
    """提供另一个不同的翻译请求对象。"""
    # 修复：添加 engine_name 和 engine_version
    return TranslationRequest(
        source_payload={"text": "World"},
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
        engine_name="debug",
        engine_version="1.0",
    )


@pytest.mark.asyncio
async def test_cache_set_and_get(sample_request: TranslationRequest) -> None:
    """测试基本的缓存设置和获取功能。"""
    cache = TranslationCache()
    assert await cache.get_cached_result(sample_request) is None
    await cache.cache_translation_result(sample_request, "Hallo")
    result = await cache.get_cached_result(sample_request)
    assert result == "Hallo"


@pytest.mark.asyncio
async def test_ttl_expiration(
    sample_request: TranslationRequest, mocker: MockerFixture
) -> None:
    """测试 TTL 缓存是否会在指定时间后自动使条目失效（确定性测试）。"""
    current_time = 1000.0

    def timer() -> float:
        return current_time

    config = CacheConfig(maxsize=10, ttl=1, cache_type=CacheType.TTL)
    cache = TranslationCache(config)
    cache.cache = TTLCache(maxsize=config.maxsize, ttl=config.ttl, timer=timer)

    await cache.cache_translation_result(sample_request, "Hallo")
    assert await cache.get_cached_result(sample_request) == "Hallo"

    current_time += 1.1

    assert await cache.get_cached_result(sample_request) is None


def test_generate_cache_key_is_hashed_and_stable(
    sample_request: TranslationRequest,
) -> None:
    """测试生成的缓存键是稳定的、基于哈希的，并且不包含原始载荷的明文。"""
    cache = TranslationCache()
    key1 = cache.generate_cache_key(sample_request)

    assert isinstance(key1, str)
    assert len(key1) < 150  # 调整预期长度以容纳新字段

    original_text = sample_request.source_payload.get("text")
    assert original_text
    assert original_text not in key1

    assert sample_request.target_lang in key1
    assert sample_request.context_hash in key1
    # 修复：验证新字段在键中
    assert sample_request.engine_name in key1
    assert sample_request.engine_version in key1

    # 修复：为新实例添加新字段
    same_request_different_instance = TranslationRequest(
        source_payload={"text": "Hello"},
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
        engine_name="debug",
        engine_version="1.0",
    )
    key2 = cache.generate_cache_key(same_request_different_instance)
    assert key1 == key2
