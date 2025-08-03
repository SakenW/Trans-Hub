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
from pytest_mock import MockerFixture

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
def test_rate_limiter_init_with_invalid_args(rate: float, capacity: float) -> None:
    """测试 RateLimiter 初始化时，能否拒绝无效的速率或容量参数。"""
    with pytest.raises(ValueError, match="速率和容量必须为正数"):
        RateLimiter(refill_rate=rate, capacity=capacity)


@pytest.mark.asyncio
async def test_acquire_succeeds_immediately_when_tokens_are_sufficient() -> None:
    """测试当令牌充足时，acquire 方法会立即成功并消耗正确的令牌数。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)
    assert limiter.tokens == 10
    await limiter.acquire(5)
    assert limiter.tokens == 5


@pytest.mark.asyncio
async def test_acquire_waits_when_tokens_are_insufficient(
    mocker: MockerFixture,
) -> None:
    """测试当令牌不足时，acquire 方法会异步等待，并且等待时间计算正确。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)
    mock_sleep = mocker.patch("asyncio.sleep", new_callable=AsyncMock)

    # 模拟时间流逝
    start_time = time.monotonic()
    time_sequence = [start_time, start_time, start_time + 0.5]

    def monotonic_side_effect() -> float:
        return time_sequence.pop(0) if time_sequence else start_time + 0.5

    mocker.patch("time.monotonic", side_effect=monotonic_side_effect)

    # 耗尽令牌
    await limiter.acquire(10)
    assert limiter.tokens == 0

    # 再次请求，此时应触发等待
    await limiter.acquire(5)

    # 验证等待时间
    mock_sleep.assert_called_once()
    waited_time = mock_sleep.call_args[0][0]
    assert pytest.approx(waited_time) == 0.5
    assert limiter.tokens == 0


@pytest.mark.asyncio
async def test_refill_logic_does_not_exceed_capacity(mocker: MockerFixture) -> None:
    """
    测试令牌的补充逻辑是否正确，且补充后的令牌数不会超过容量上限。

    v3.1 修复：此测试现在通过公共接口 `acquire` 来验证行为，而不是调用
    私有方法 `_refill`，遵循了“行为驱动测试”的原则。

    Args:
        mocker: pytest-mock 提供的 mocker fixture。
    """
    limiter = RateLimiter(refill_rate=10, capacity=10)
    # 消耗一些令牌
    limiter.tokens = 2
    start_time = limiter.last_refill_time

    # 模拟时间流逝了2秒，足以完全填满令牌桶
    mocker.patch("time.monotonic", return_value=start_time + 2)

    # 请求1个令牌，这将触发一次补充
    await limiter.acquire(1)

    # 验证：补充后，剩余令牌应为 capacity - 1，而不是 2 + (10*2) - 1
    assert limiter.tokens == 9  # 10 (capacity) - 1 (acquired) = 9


@pytest.mark.asyncio
async def test_acquire_more_than_capacity_raises_error() -> None:
    """测试当请求的令牌数超过桶的总容量时，应立即抛出 ValueError。"""
    limiter = RateLimiter(refill_rate=10, capacity=10)
    with pytest.raises(ValueError, match="请求的令牌数不能超过桶的容量"):
        await limiter.acquire(11)