# trans_hub/rate_limiter.py
"""本模块提供一个基于令牌桶算法的异步速率限制器。"""

import asyncio
import time


class RateLimiter:
    """一个异步安全的令牌桶（Token Bucket）速率限制器。"""

    def __init__(self, refill_rate: float, capacity: float):
        if refill_rate <= 0 or capacity <= 0:
            raise ValueError("速率和容量必须为正数")
        self.refill_rate = refill_rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill_time = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """[私有] 根据流逝的时间补充令牌。"""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        if elapsed > 0:
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill_time = now

    async def acquire(self, tokens_needed: int = 1) -> None:
        """异步获取指定数量的令牌，如果令牌不足则等待。"""
        if tokens_needed > self.capacity:
            raise ValueError("请求的令牌数不能超过桶的容量")

        # v3.x 修复：重构锁的获取和释放，避免在 sleep 时持有锁，以提高并发效率
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= tokens_needed:
                    self.tokens -= tokens_needed
                    return  # 成功获取令牌，退出

                # 在锁内计算等待时间，以确保状态一致
                required = tokens_needed - self.tokens
                wait_time = required / self.refill_rate

            # 在锁外等待，允许其他协程并发地计算和进入等待状态
            await asyncio.sleep(wait_time)
