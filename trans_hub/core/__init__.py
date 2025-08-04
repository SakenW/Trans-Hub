# trans_hub/core/__init__.py
"""
本核心包定义了 Trans-Hub 系统中最基础、最稳定的构建块。

这里包含了系统的核心数据类型、接口协议和自定义异常，它们共同构成了
整个应用的“契约”。所有其他模块都依赖于此核心包，但本包不依赖于
项目中的任何其他模块。
"""

from .exceptions import (
    APIError,
    ConfigurationError,
    DatabaseError,
    EngineNotFoundError,
    TransHubError,
)
from .interfaces import PersistenceHandler
from .types import (
    GLOBAL_CONTEXT_SENTINEL,
    ContentItem,
    EngineBatchItemResult,
    EngineError,
    EngineSuccess,
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)

__all__ = [
    # from exceptions.py
    "TransHubError",
    "ConfigurationError",
    "EngineNotFoundError",
    "DatabaseError",
    "APIError",
    # from interfaces.py
    "PersistenceHandler",
    # from types.py
    "TranslationStatus",
    "EngineSuccess",
    "EngineError",
    "EngineBatchItemResult",
    "TranslationRequest",
    "TranslationResult",
    "ContentItem",
    "GLOBAL_CONTEXT_SENTINEL",
]
