# tests/unit/test_cache.py
"""
针对 `trans_hub.cache` 模块的单元测试。
"""
import pytest
from cachetools import TTLCache
from pytest_mock import MockerFixture

from trans_hub.cache import CacheConfig, TranslationCache
from trans_hub.core.types import TranslationRequest


@pytest.fixture
def sample_request() -> TranslationRequest:
    """提供一个可复用的翻译请求对象。"""
    return TranslationRequest(
        source_payload={"text": "Hello"},
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
    )


@pytest.fixture
def another_request() -> TranslationRequest:
    """提供另一个不同的翻译请求对象。"""
    return TranslationRequest(
        source_payload={"text": "World"},
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
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

    config = CacheConfig(maxsize=10, ttl=1, cache_type="ttl")
    cache = TranslationCache(config)
    cache.cache = TTLCache(maxsize=config.maxsize, ttl=config.ttl, timer=timer)

    await cache.cache_translation_result(sample_request, "Hallo")
    assert await cache.get_cached_result(sample_request) == "Hallo"

    current_time += 1.1

    assert await cache.get_cached_result(sample_request) is None