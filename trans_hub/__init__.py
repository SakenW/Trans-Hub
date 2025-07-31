# trans_hub/__init__.py
"""Trans-Hub: 是一个可嵌入的、带持久化存储的智能本地化后端引擎。

该模块提供了核心的协调器和配置管理功能，用于处理多语言翻译任务。
"""

__version__ = "3.0.0.dev0"

from .config import EngineName, TransHubConfig
from .coordinator import Coordinator
from .engines.base import BaseContextModel
from .persistence import DefaultPersistenceHandler, create_persistence_handler
from .types import TranslationStatus

__all__ = [
    "__version__",
    "Coordinator",
    "TransHubConfig",
    "EngineName",
    "TranslationStatus",
    "BaseContextModel",
    "DefaultPersistenceHandler",
    "create_persistence_handler",
]
