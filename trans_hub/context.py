# trans_hub/context.py
"""定义处理流程中使用的高层上下文对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter


@dataclass(frozen=True)
class ProcessingContext:
    """一个“工具箱”对象，封装了处理策略执行时所需的所有依赖项。"""

    # 核心依赖组件
    config: TransHubConfig
    handler: PersistenceHandler
    cache: TranslationCache

    # 可选依赖组件
    rate_limiter: Optional[RateLimiter] = None
