# trans_hub/engine_registry.py (最终优化版)
"""负责动态发现和加载可用的翻译引擎。."""

import importlib
import pkgutil

import structlog

from trans_hub.engines.base import BaseTranslationEngine

log = structlog.get_logger(__name__)
ENGINE_REGISTRY: dict[str, type[BaseTranslationEngine]] = {}


def discover_engines():
    """
    动态发现 `trans_hub.engines` 包下的所有引擎并尝试注册。
    此函数是幂等的，只会执行一次。.
    """
    if ENGINE_REGISTRY:
        return

    import trans_hub.engines

    log.info("开始发现可用引擎...", path=trans_hub.engines.__path__)

    for module_info in pkgutil.iter_modules(trans_hub.engines.__path__):
        module_name = module_info.name
        # 跳过基类模块和私有模块
        if module_name in ["base"] or module_name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"trans_hub.engines.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # --- 核心修正：添加额外的类型检查以增强健壮性 ---
                # 确保 attr 是一个类，而不是函数或变量
                if not isinstance(attr, type):
                    continue

                try:
                    # 检查它是否是我们正在寻找的引擎子类
                    if (
                        issubclass(attr, BaseTranslationEngine)
                        and attr is not BaseTranslationEngine
                    ):
                        # 约定：从类名自动推断引擎的注册名
                        engine_name = attr.__name__.replace("Engine", "").lower()
                        ENGINE_REGISTRY[engine_name] = attr
                        log.info("✅ 成功发现并注册引擎", engine_name=engine_name)
                except TypeError:
                    # 捕获 `issubclass` 可能对某些特殊对象抛出的 TypeError，
                    # 确保加载过程不会被意外中断。
                    continue

        except ModuleNotFoundError as e:
            # 优雅地处理缺少可选依赖的情况
            log.warning(
                "⚠️ 跳过加载引擎，因缺少依赖",
                engine_name=module_name,
                missing_dependency=e.name,
            )
        except Exception:
            log.error(
                "加载引擎模块时发生未知错误", module_name=module_name, exc_info=True
            )


# 在模块首次被导入时，自动执行一次发现
discover_engines()
