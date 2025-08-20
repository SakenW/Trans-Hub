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
    Event, ProcessingContext, TranslationHead, TranslationRevision,
    TranslationStatus,
)
# [新增] 导出 UoW 和仓库协议
from .uow import (
    IContentRepository, ITranslationRepository, ITmRepository,
    IMiscRepository, IUnitOfWork, IOutboxRepository
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
    "EngineBatchItemResult", "ContentItem", "ProcessingContext",
    "TranslationHead", "TranslationRevision", "Comment", "Event",
    # [新增] from uow.py
    "IUnitOfWork", "IContentRepository", "ITranslationRepository",
    "ITmRepository", "IMiscRepository", "IOutboxRepository"
]