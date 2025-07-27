# trans_hub/__init__.py
"""Trans-Hub: 异步本地化后端引擎"""

__version__ = "3.0.0.dev0"

from .config import TransHubConfig
from .coordinator import Coordinator
from .engines.base import BaseContextModel
from .persistence import DefaultPersistenceHandler  # <-- 核心修正：重新暴露
from .types import TranslationStatus

__all__ = [
    "__version__",
    "TransHubConfig",
    "Coordinator",
    "BaseContextModel",
    "DefaultPersistenceHandler",  # <-- 核心修正：重新暴露
    "TranslationStatus",
]
