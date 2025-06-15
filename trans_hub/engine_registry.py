"""trans_hub/engine_registry.py

负责动态发现和加载可用的翻译引擎。
"""

import importlib
import pkgutil

import structlog

from trans_hub.engines.base import BaseTranslationEngine

log = structlog.get_logger(__name__)
ENGINE_REGISTRY: dict[str, type[BaseTranslationEngine]] = {}


def discover_engines():
    """动态发现 `trans_hub.engines` 包下的所有引擎并尝试注册。"""
    if ENGINE_REGISTRY:
        return

    import trans_hub.engines

    log.info("开始发现可用引擎...", path=trans_hub.engines.__path__)
    for module_info in pkgutil.iter_modules(trans_hub.engines.__path__):
        module_name = module_info.name
        if module_name in ["base"]:
            continue

        try:
            module = importlib.import_module(f"trans_hub.engines.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseTranslationEngine)
                    and attr is not BaseTranslationEngine
                ):
                    engine_name = attr.__name__.replace("Engine", "").lower()
                    ENGINE_REGISTRY[engine_name] = attr
                    log.info("✅ 成功发现并注册引擎", engine_name=engine_name)
        except ModuleNotFoundError as e:
            log.warning(
                "⚠️ 跳过加载引擎，因缺少依赖",
                engine_name=module_name,
                missing_dependency=e.name,
            )
        except Exception:
            log.error(
                "加载引擎模块时发生未知错误", module_name=module_name, exc_info=True
            )


# 在模块加载时自动执行一次发现
discover_engines()
