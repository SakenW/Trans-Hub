# trans_hub/context.py
"""定义处理流程中使用的高层上下文对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter

# --- 核心修正 1.2.1: 解决循环导入问题 ---
if TYPE_CHECKING:
    from trans_hub.coordinator import Coordinator


@dataclass(frozen=True)
class ProcessingContext:
    """一个“工具箱”对象，封装了处理策略执行时所需的所有依赖项。"""

    # 核心依赖组件
    config: TransHubConfig
    handler: PersistenceHandler
    cache: TranslationCache

    # --- 核心修正 1.2.1: 引用 Coordinator 以访问引擎实例缓存 ---
    coordinator: Coordinator

    # 可选依赖组件
    rate_limiter: Optional[RateLimiter] = None

    @property
    def active_engine(self) -> BaseTranslationEngine:
        """从 Coordinator 的缓存中动态获取当前的活动翻译引擎实例。"""
        engine_name = self.config.active_engine.value
        # 直接调用 coordinator 的方法来获取实例
        return self.coordinator._get_or_create_engine_instance(engine_name)
