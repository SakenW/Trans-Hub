# trans_hub/engines/meta.py
"""定义了引擎元数据的中心化注册表。"""

from pydantic import BaseModel

ENGINE_CONFIG_REGISTRY: dict[str, type[BaseModel]] = {}


def register_engine_config(name: str, config_class: type[BaseModel]) -> None:
    """一个供所有引擎模块在加载时调用的注册函数。"""
    if name in ENGINE_CONFIG_REGISTRY:
        return
    ENGINE_CONFIG_REGISTRY[name] = config_class
