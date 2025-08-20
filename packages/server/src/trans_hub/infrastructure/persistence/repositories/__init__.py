# packages/server/src/trans_hub/infrastructure/persistence/repositories/__init__.py
from ._content_repo import SqlAlchemyContentRepository
from ._translation_repo import SqlAlchemyTranslationRepository
from ._tm_repo import SqlAlchemyTmRepository
from ._misc_repo import SqlAlchemyMiscRepository
from ._outbox_repo import SqlAlchemyOutboxRepository  # [修复] 导出 Outbox 仓库

__all__ = [
    "SqlAlchemyContentRepository",
    "SqlAlchemyTranslationRepository",
    "SqlAlchemyTmRepository",
    "SqlAlchemyMiscRepository",
    "SqlAlchemyOutboxRepository",  # [修复] 添加到 __all__
]