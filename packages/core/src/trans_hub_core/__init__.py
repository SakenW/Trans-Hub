# packages/core/src/trans_hub_core/__init__.py
"""
Trans-Hub 核心契约包。
...
"""
from .exceptions import (
    APIError, ConfigurationError, DatabaseError,
    EngineNotFoundError, TransHubError, LockAcquisitionError,
)
from .interfaces import (
    CacheHandler, LockProvider,
    QueueProducer, StreamProducer, RateLimiter,
)
from .types import (
    Comment, ContentItem, EngineBatchItemResult, EngineError, EngineSuccess,
    Event, TranslationHead, TranslationRevision,
    TranslationStatus,
)
# [修复] 从 uow 导入 IOutboxRepository
from .uow import (
    IContentRepository, ITranslationRepository, ITmRepository,
    IMiscRepository, IOutboxRepository, IUnitOfWork
)

__all__ = [
    # from exceptions.py
    "TransHubError", "ConfigurationError", "EngineNotFoundError",
    "DatabaseError", "APIError", "LockAcquisitionError",
    # from interfaces.py
    "CacheHandler", "LockProvider",
    "RateLimiter", "QueueProducer", "StreamProducer",
    # from types.py
    "TranslationStatus", "EngineSuccess", "EngineError",
    "EngineBatchItemResult", "ContentItem",
    "TranslationHead", "TranslationRevision", "Comment", "Event",
    # from uow.py
    "IUnitOfWork", "IContentRepository", "ITranslationRepository",
    "ITmRepository", "IMiscRepository", "IOutboxRepository", # [修复] 添加到 __all__
]
