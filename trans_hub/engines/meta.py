# trans_hub/engines/meta.py
"""
定义了引擎元数据的中心化注册表。

这个模块处于依赖链的底层，用于解耦 `config` 模块和具体的引擎实现。
引擎模块在被加载时，会通过调用 `register_engine_config` 来向此处的
注册表“报告”自己的配置模型。
"""

from pydantic import BaseModel

# 这个字典将存储: {'engine_name': EngineConfigClass, ...}
# 例如: {'debug': DebugEngineConfig, 'openai': OpenAIEngineConfig}
ENGINE_CONFIG_REGISTRY: dict[str, type[BaseModel]] = {}


def register_engine_config(name: str, config_class: type[BaseModel]):
    """
    一个供所有引擎模块在加载时调用的注册函数。

    Args:
    ----
        name (str): 引擎的名称 (例如, "debug", "openai")。
        config_class (Type[BaseModel]): 引擎对应的配置模型类
                                        (例如, DebugEngineConfig)。

    """
    if name in ENGINE_CONFIG_REGISTRY:
        # 在测试场景下，模块可能被多次加载，这里做一个简单的幂等性处理
        return
    ENGINE_CONFIG_REGISTRY[name] = config_class
