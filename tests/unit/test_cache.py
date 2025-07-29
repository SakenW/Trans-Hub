# tests/unit/test_cache.py
"""
针对 `trans_hub.cache` 模块的单元测试。

这些测试验证了 TranslationCache 的核心功能，包括基本的缓存操作、
TTL（生存时间）过期策略以及 LRU（最近最少使用）淘汰策略。
"""

import asyncio

import pytest

from trans_hub.cache import CacheConfig, TranslationCache
from trans_hub.types import TranslationRequest


@pytest.fixture
def sample_request() -> TranslationRequest:
    """提供一个可复用的翻译请求对象。"""
    return TranslationRequest(
        source_text="Hello",
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
    )


@pytest.fixture
def another_request() -> TranslationRequest:
    """提供另一个不同的翻译请求对象。"""
    return TranslationRequest(
        source_text="World",
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
async def test_ttl_expiration(sample_request: TranslationRequest) -> None:
    """测试 TTL 缓存是否会在指定时间后自动使条目失效。"""
    config = CacheConfig(maxsize=10, ttl=1, cache_type="ttl")
    cache = TranslationCache(config)

    await cache.cache_translation_result(sample_request, "Hallo")
    assert await cache.get_cached_result(sample_request) == "Hallo"

    await asyncio.sleep(1.1)
    assert await cache.get_cached_result(sample_request) is None


@pytest.mark.asyncio
async def test_lru_eviction(
    sample_request: TranslationRequest, another_request: TranslationRequest
) -> None:
    """测试 LRU 缓存在容量满时，是否会淘汰最近最少使用的条目。"""
    config = CacheConfig(maxsize=2, cache_type="lru")
    cache = TranslationCache(config)
    third_request = TranslationRequest(
        source_text="Test",
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
    )

    await cache.cache_translation_result(sample_request, "Hallo")
    await cache.cache_translation_result(another_request, "Welt")
    await cache.get_cached_result(sample_request)
    await cache.cache_translation_result(third_request, "Testen")

    assert await cache.get_cached_result(sample_request) == "Hallo"
    assert await cache.get_cached_result(third_request) == "Testen"
    assert await cache.get_cached_result(another_request) is None


@pytest.mark.asyncio
async def test_clear_cache(sample_request: TranslationRequest) -> None:
    """测试 clear_cache 方法是否能清空所有缓存条目。"""
    cache = TranslationCache()
    await cache.cache_translation_result(sample_request, "Hallo")
    assert await cache.get_cached_result(sample_request) is not None
    await cache.clear_cache()
    assert await cache.get_cached_result(sample_request) is None
