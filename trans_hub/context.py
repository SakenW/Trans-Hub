# trans_hub/context.py
"""
定义处理流程中使用的高层上下文对象。

这个模块处于依赖链的高层，可以安全地导入应用中的任何其他组件。
"""

from dataclasses import dataclass
from typing import Optional

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter


@dataclass(frozen=True)
class ProcessingContext:
    """
    一个“工具箱”对象，封装了处理策略执行时所需的所有依赖项。

    使用标准的 `dataclass` 而非 Pydantic `BaseModel`，以避免对 Protocol
    等非类类型进行不必要的运行时验证。`frozen=True` 确保了上下文在
    处理流程中的不可变性，提高了代码的健壮性。
    """

    # 核心依赖组件
    config: TransHubConfig
    handler: PersistenceHandler
    cache: TranslationCache

    # 可选依赖组件
    rate_limiter: Optional[RateLimiter] = None

    @property
    def active_engine(self) -> BaseTranslationEngine:
        """动态获取并返回当前的活动翻译引擎实例。"""
        engine_name = self.config.active_engine
        engine_class = ENGINE_REGISTRY[engine_name]
        engine_config_instance = getattr(self.config.engine_configs, engine_name)
        return engine_class(config=engine_config_instance)
