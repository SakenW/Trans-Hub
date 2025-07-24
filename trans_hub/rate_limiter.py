# trans_hub/rate_limiter.py (修正后)
"""提供一个基于令牌桶算法的异步速率限制器。."""

import asyncio
import time


class RateLimiter:
    """一个异步安全的令牌桶速率限制器。
    它允许在一段时间内平滑地处理请求，以应对突发流量。.
    """

    def __init__(self, refill_rate: float, capacity: float):
        if refill_rate <= 0 or capacity <= 0:
            raise ValueError("速率和容量必须为正数")
        self.refill_rate = refill_rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill_time = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        """[私有] 根据流逝的时间补充令牌。此方法不是线程/任务安全的。."""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        if elapsed > 0:
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill_time = now

    async def acquire(self, tokens_needed: int = 1) -> None:
        """获取指定数量的令牌，如果令牌不足则异步等待。."""
        if tokens_needed > self.capacity:
            raise ValueError("请求的令牌数不能超过桶的容量")

        async with self._lock:
            self._refill()

            while self.tokens < tokens_needed:
                # 计算需要等待的时间
                required = tokens_needed - self.tokens
                wait_time = required / self.refill_rate

                # 异步等待
                await asyncio.sleep(wait_time)

                # 等待后再次补充
                self._refill()

            self.tokens -= tokens_needed
