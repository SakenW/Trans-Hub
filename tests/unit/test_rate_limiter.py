# tests/unit/test_rate_limiter.py
"""
针对 `trans_hub.rate_limiter` 模块的单元测试。

这些测试验证了基于令牌桶算法的 RateLimiter 的核心逻辑，
包括令牌的消耗、补充以及在令牌不足时的异步等待行为。
"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from trans_hub.rate_limiter import RateLimiter


@pytest.mark.parametrize(
    "rate, capacity",
    [
        (0, 10),
        (-1, 10),
        (10, 0),
        (10, -1),
    ],
)
def test_rate_limiter_init_with_invalid_args(rate: float, capacity: float):
    """测试 RateLimiter 初始化时，能否拒绝无效的速率或容量参数。"""
    with pytest.raises(ValueError, match="速率和容量必须为正数"):
        RateLimiter(refill_rate=rate, capacity=capacity)


@pytest.mark.asyncio
async def test_acquire_succeeds_immediately_when_tokens_are_sufficient():
    """测试当令牌充足时，acquire 方法会立即成功并消耗正确的令牌数。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)

    assert limiter.tokens == 10
    await limiter.acquire(5)
    assert limiter.tokens == 5


@pytest.mark.asyncio
async def test_acquire_waits_when_tokens_are_insufficient(monkeypatch):
    """测试当令牌不足时，acquire 方法会异步等待，并且等待时间计算正确。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)

    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    # --- 核心修正：使用函数来提供更健壮的 side_effect ---
    start_time = time.monotonic()
    # 定义一个时间序列，模拟每次调用 time.monotonic() 的返回值
    time_sequence = [
        start_time,  # 第一次调用（消耗令牌前）
        start_time,  # 第二次调用（计算等待时间时）
        start_time + 0.5,  # 第三次调用（等待后补充令牌时）
    ]

    def monotonic_side_effect():
        # 如果序列不为空，则弹出第一个值，否则返回最后一个值
        if time_sequence:
            return time_sequence.pop(0)
        return start_time + 0.5

    monkeypatch.setattr(time, "monotonic", monotonic_side_effect)

    # 行动 1：消耗所有令牌
    await limiter.acquire(10)
    assert limiter.tokens == 0

    # 行动 2：再次请求 5 个令牌，此时应该会触发等待
    await limiter.acquire(5)

    # 断言：
    mock_sleep.assert_called_once()
    waited_time = mock_sleep.call_args[0][0]
    assert pytest.approx(waited_time) == 0.5
    assert limiter.tokens == 0


@pytest.mark.asyncio
async def test_refill_logic(monkeypatch):
    """测试令牌的补充逻辑是否正确，且不会超过容量上限。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)

    limiter.tokens = 5

    start_time = limiter.last_refill_time
    monkeypatch.setattr(time, "monotonic", lambda: start_time + 2)

    limiter._refill()

    assert limiter.tokens == 10

    limiter.tokens -= 1
    assert limiter.tokens == 9


@pytest.mark.asyncio
async def test_acquire_more_than_capacity_raises_error():
    """测试当请求的令牌数超过桶容量时，应立即抛出 ValueError。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)

    with pytest.raises(ValueError, match="请求的令牌数不能超过桶的容量"):
        await limiter.acquire(11)


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])
