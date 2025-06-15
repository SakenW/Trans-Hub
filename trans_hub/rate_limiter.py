"""trans_hub/rate_limiter.py (v0.1)

提供一个简单的、基于令牌桶算法的同步速率限制器。
"""

import time
from threading import Lock


class RateLimiter:
    """一个简单的令牌桶速率限制器。

    它允许在一段时间内平滑地处理请求，而不是严格地每秒固定次数。
    这对于应对突发流量非常有效。

    算法:
    - 桶有一个固定的容量 (capacity)。
    - 令牌以固定的速率 (refill_rate) 被添加到桶中。
    - 每次操作需要从桶中取出一个令牌。
    - 如果桶中没有令牌，操作必须等待，直到有新的令牌被添加进来。
    """

    def __init__(self, refill_rate: float, capacity: float):
        """初始化速率限制器。

        Args:
        ----
            refill_rate: 每秒补充的令牌数量 (例如, 10 表示 10 rps)。
            capacity: 桶的最大容量 (通常等于或略大于 refill_rate)。

        """
        if refill_rate <= 0 or capacity <= 0:
            raise ValueError("速率和容量必须为正数")

        self.refill_rate = refill_rate
        self.capacity = capacity
        self.tokens = capacity  # 初始时，桶是满的
        self.last_refill_time = time.monotonic()
        self._lock = Lock()  # 确保在多线程环境下的线程安全

    def _refill(self):
        """根据流逝的时间补充令牌。"""
        now = time.monotonic()
        elapsed = now - self.last_refill_time

        # 计算这段时间内应该补充的令牌数
        tokens_to_add = elapsed * self.refill_rate

        # 更新桶中的令牌数，但不能超过容量上限
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill_time = now

    def acquire(self, tokens_needed: int = 1) -> None:
        """获取指定数量的令牌，如果令牌不足则阻塞等待。

        Args:
        ----
            tokens_needed: 本次操作需要消耗的令牌数量。

        """
        if tokens_needed > self.capacity:
            raise ValueError("请求的令牌数不能超过桶的容量")

        with self._lock:
            # 检查是否有足够的令牌，如果没有，则循环等待
            while tokens_needed > self.tokens:
                # 在等待前，先尝试补充令牌
                self._refill()

                # 如果补充后仍然不够，计算需要等待多长时间
                if tokens_needed > self.tokens:
                    required = tokens_needed - self.tokens
                    wait_time = required / self.refill_rate
                    time.sleep(wait_time)

                # 再次补充，因为我们刚刚等待了一段时间
                self._refill()

            # 消耗令牌
            self.tokens -= tokens_needed
