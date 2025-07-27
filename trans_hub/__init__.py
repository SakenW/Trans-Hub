# trans_hub/__init__.py
"""Trans-Hub: 异步本地化后端引擎"""

__version__ = "3.0.0.dev0"  # <-- 更新版本号

from .config import TransHubConfig
from .coordinator import Coordinator
from .engines.base import BaseContextModel # <-- 暴露给使用者
from .types import TranslationStatus

__all__ = [
    "__version__",
    "TransHubConfig",
    "Coordinator",
    "BaseContextModel",  # <-- 新增
    "TranslationStatus",
]