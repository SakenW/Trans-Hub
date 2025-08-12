# src/trans_hub_core/__init__.py
"""
Trans-Hub 核心契约包。

本包定义了整个 Trans-Hub 生态系统共享的基础组件，包括：
- `interfaces`: 系统各层之间交互的协议 (Protocols)。
- `types`: 核心的数据结构和枚举。
- `exceptions`: 自定义的、具有明确语义的异常类。

作为系统的基石，本包不依赖于任何其他内部包，并且应保持尽可能的稳定。
"""
from .exceptions import (
    APIError,
    ConfigurationError,
    DatabaseError,
    EngineNotFoundError,
    TransHubError,
    LockAcquisitionError,
)
from .interfaces import (
    CacheHandler,
    LockProvider,
    PersistenceHandler,
    QueueProducer,
    StreamProducer,
)
from .types import (
    Comment,
    ContentItem,
    EngineBatchItemResult,
    EngineError,
    EngineSuccess,
    Event,
    ProcessingContext,
    TranslationHead,
    TranslationRevision,
    TranslationStatus,
)

__all__ = [
    # from exceptions.py
    "TransHubError",
    "ConfigurationError",
    "EngineNotFoundError",
    "DatabaseError",
    "APIError",
    "LockAcquisitionError",
    # from interfaces.py
    "PersistenceHandler",
    "CacheHandler",
    "LockProvider",
    "RateLimiter",
    "QueueProducer",
    "StreamProducer",
    # from types.py
    "TranslationStatus",
    "EngineSuccess",
    "EngineError",
    "EngineBatchItemResult",
    "ContentItem",
    "ProcessingContext",
    "TranslationHead",
    "TranslationRevision",
    "Comment",
    "Event",
]