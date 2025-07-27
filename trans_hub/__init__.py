# trans_hub/__init__.py
"""Trans-Hub: 异步本地化后端引擎"""

__version__ = "3.0.0.dev0"

# --- 核心修正：从 config 模块中导入并暴露 EngineName ---
from .config import EngineName, TransHubConfig
from .coordinator import Coordinator
from .engines.base import BaseContextModel
from .persistence import DefaultPersistenceHandler
from .types import TranslationStatus

__all__ = [
    "__version__",
    "TransHubConfig",
    "Coordinator",
    "BaseContextModel",
    "DefaultPersistenceHandler",
    "TranslationStatus",
    "EngineName",  # <-- 将 EngineName 添加到 __all__
]
