# trans_hub/engine_registry.py
"""本模块负责动态发现和加载 `trans_hub.engines` 包下所有可用的翻译引擎。"""

import importlib
import pkgutil
from typing import Any, Dict, List

import structlog

from trans_hub.engines.base import BaseTranslationEngine

log = structlog.get_logger(__name__)
ENGINE_REGISTRY: Dict[str, type[BaseTranslationEngine[Any]]] = {}


def discover_engines() -> None:
    """
    动态发现 `trans_hub.engines` 包下的所有引擎并注册。

    此函数被设计为幂等的，只在首次调用时执行发现操作。
    它应该在日志系统配置完成后被调用，以确保正确的日志输出格式。
    """
    if ENGINE_REGISTRY:
        return

    import trans_hub.engines

    successful_engines: List[str] = []
    skipped_engines: List[Dict[str, str]] = []

    for module_info in pkgutil.iter_modules(trans_hub.engines.__path__):
        module_name = module_info.name
        if module_name in ["base", "meta"] or module_name.startswith("_"):
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
                    successful_engines.append(engine_name)
        except ImportError as e:
            skipped_engines.append(
                {"engine_name": module_name, "missing_dependency": str(e.name)}
            )
        except Exception:
            log.error(
                "加载引擎模块时发生未知错误", module_name=module_name, exc_info=True
            )
            skipped_engines.append(
                {"engine_name": module_name, "missing_dependency": "未知错误"}
            )

    # 在所有发现操作完成后，记录一次性的摘要日志
    log_payload: Dict[str, Any] = {"path": trans_hub.engines.__path__}
    if successful_engines:
        log_payload["✅ 已注册"] = sorted(successful_engines)
    if skipped_engines:
        log_payload["⚠️ 已跳过"] = skipped_engines

    log.info("引擎发现完成。", **log_payload)


# v3.1 最终修复：移除在模块顶层的调用，改为由 Coordinator 在初始化时调用。
# discover_engines()
