# packages/server/src/trans_hub/infrastructure/engines/__init__.py
"""
本模块负责动态发现和加载所有可用的翻译引擎。
"""

import importlib
import pkgutil
from typing import Any

import structlog

# from .base import BaseTranslationEngine # 避免循环导入

logger = structlog.get_logger(__name__)
ENGINE_REGISTRY: dict[str, Any] = {}  # dict[str, type[BaseTranslationEngine[Any]]]


def discover_engines() -> None:
    """
    动态发现本包下的所有引擎并注册。
    此函数被设计为幂等的，只在首次调用时执行发现操作。
    """
    if ENGINE_REGISTRY:
        return

    from . import base

    successful_engines: list[str] = []

    for module_info in pkgutil.iter_modules(__path__):
        module_name = module_info.name
        if module_name in ["base"] or module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"{__name__}.{module_name}")
            for attr in vars(module).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, base.BaseTranslationEngine)
                    and attr is not base.BaseTranslationEngine
                ):
                    engine_name = attr.name()
                    ENGINE_REGISTRY[engine_name] = attr
                    successful_engines.append(engine_name)
        except Exception:
            logger.warning("加载引擎模块时出错", module=module_name, exc_info=True)

    logger.info("引擎发现完成。", loaded_engines=sorted(successful_engines))
