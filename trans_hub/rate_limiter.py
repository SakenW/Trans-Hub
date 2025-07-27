# trans_hub/rate_limiter.py
"""
本模块提供一个基于令牌桶算法的异步速率限制器。

它旨在平滑处理突发请求，防止对下游服务（如翻译API）造成过大压力。
"""

import asyncio
import time


class RateLimiter:
    """
    一个异步安全的令牌桶（Token Bucket）速率限制器。

    它以恒定的速率 (`refill_rate`) 向桶中添加令牌，直到达到容量 (`capacity`) 上限。
    每次请求需要消耗一个或多个令牌，如果令牌不足，请求将异步等待直到令牌可用。
    """

    def __init__(self, refill_rate: float, capacity: float):
        """
        初始化速率限制器。

        参数:
            refill_rate: 每秒补充的令牌数量。
            capacity: 桶的最大容量。
        """
        if refill_rate <= 0 or capacity <= 0:
            raise ValueError("速率和容量必须为正数")
        self.refill_rate = refill_rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill_time = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        """[私有] 根据流逝的时间补充令牌。此方法不是任务安全的，必须在锁内调用。"""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        if elapsed > 0:
            tokens_to_add = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill_time = now

    async def acquire(self, tokens_needed: int = 1) -> None:
        """
        异步获取指定数量的令牌，如果令牌不足则等待。

        参数:
            tokens_needed: 本次操作需要消耗的令牌数量。
        """
        if tokens_needed > self.capacity:
            raise ValueError("请求的令牌数不能超过桶的容量")

        async with self._lock:
            self._refill()

            while self.tokens < tokens_needed:
                required = tokens_needed - self.tokens
                wait_time = required / self.refill_rate
                await asyncio.sleep(wait_time)
                self._refill()

            self.tokens -= tokens_needed
