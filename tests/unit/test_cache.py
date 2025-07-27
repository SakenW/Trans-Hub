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
async def test_cache_set_and_get(sample_request: TranslationRequest):
    """测试基本的缓存设置和获取功能。"""
    cache = TranslationCache()

    # 初始状态应为空
    assert await cache.get_cached_result(sample_request) is None

    # 设置缓存
    await cache.cache_translation_result(sample_request, "Hallo")

    # 验证可以获取到值
    result = await cache.get_cached_result(sample_request)
    assert result == "Hallo"


@pytest.mark.asyncio
async def test_cache_miss(sample_request: TranslationRequest):
    """测试当缓存中不存在键时，返回 None。"""
    cache = TranslationCache()
    assert await cache.get_cached_result(sample_request) is None


@pytest.mark.asyncio
async def test_ttl_expiration(sample_request: TranslationRequest):
    """测试 TTL 缓存是否会在指定时间后自动使条目失效。"""
    # --- 核心修正：将 ttl 从浮点数 0.1 改为整数 1 ---
    # 安排：创建一个 TTL 极短的缓存
    config = CacheConfig(maxsize=10, ttl=1, cache_type="ttl")
    cache = TranslationCache(config)

    # 行动与断言 1：设置后立即获取，应该能获取到
    await cache.cache_translation_result(sample_request, "Hallo")
    assert await cache.get_cached_result(sample_request) == "Hallo"

    # --- 核心修正：相应地增加等待时间 ---
    # 行动与断言 2：等待超过 TTL 时间后获取，应该返回 None
    await asyncio.sleep(1.1)
    assert await cache.get_cached_result(sample_request) is None


@pytest.mark.asyncio
async def test_lru_eviction(
    sample_request: TranslationRequest, another_request: TranslationRequest
):
    """测试 LRU 缓存在容量满时，是否会淘汰最近最少使用的条目。"""
    # 安排：创建一个容量为 2 的 LRU 缓存
    config = CacheConfig(maxsize=2, cache_type="lru")
    cache = TranslationCache(config)

    third_request = TranslationRequest(
        source_text="Test",
        source_lang="en",
        target_lang="de",
        context_hash="__GLOBAL__",
    )

    # 行动 1：填满缓存
    await cache.cache_translation_result(sample_request, "Hallo")  # 最近使用: sample
    await cache.cache_translation_result(
        another_request, "Welt"
    )  # 最近使用: another, sample

    # 行动 2：访问 sample_request，使其成为“最近使用”的
    await cache.get_cached_result(sample_request)  # 最近使用: sample, another
    # 此时 another_request 是最久未使用的

    # 行动 3：添加第三个元素，这应该会触发淘汰
    await cache.cache_translation_result(third_request, "Testen")

    # 断言：
    assert await cache.get_cached_result(sample_request) == "Hallo"  # 存在
    assert await cache.get_cached_result(third_request) == "Testen"  # 存在
    assert await cache.get_cached_result(another_request) is None  # 已被淘汰


@pytest.mark.asyncio
async def test_clear_cache(sample_request: TranslationRequest):
    """测试 clear_cache 方法是否能清空所有缓存条目。"""
    cache = TranslationCache()
    await cache.cache_translation_result(sample_request, "Hallo")

    # 确认值存在
    assert await cache.get_cached_result(sample_request) is not None

    # 清空缓存
    await cache.clear_cache()

    # 确认值已不存在
    assert await cache.get_cached_result(sample_request) is None


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])
