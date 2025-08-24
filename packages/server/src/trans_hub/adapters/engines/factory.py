# packages/server/src/trans_hub/adapters/engines/factory.py
"""
翻译引擎工厂

本模块负责根据应用配置，动态地发现、加载和实例化具体的翻译引擎。
这是实现引擎热插拔和解耦的核心。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from trans_hub_core.exceptions import ConfigurationError, EngineNotFoundError

from . import ENGINE_REGISTRY, discover_engines

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig

    from .base import BaseTranslationEngine

logger = structlog.get_logger(__name__)


def create_engine_instance(
    config: "TransHubConfig", engine_name: str
) -> "BaseTranslationEngine[Any]":
    """
    根据给定的引擎名称，创建并返回一个已初始化的翻译引擎实例。

    Args:
        config: 完整的应用配置对象。
        engine_name: 要实例化的引擎的名称 (如 'debug', 'openai')。

    Returns:
        一个 BaseTranslationEngine 的子类实例。

    Raises:
        EngineNotFoundError: 如果请求的引擎未注册。
        ConfigurationError: 如果引擎所需的配置缺失或无效。
    """
    discover_engines()  # 确保所有引擎都已被发现和注册

    engine_class = ENGINE_REGISTRY.get(engine_name)
    if not engine_class:
        raise EngineNotFoundError(
            f"引擎 '{engine_name}' 未找到。已注册的引擎: {list(ENGINE_REGISTRY.keys())}"
        )

    # [关键修复] 构造正确的配置属性名，例如 'openai' -> 'openai'，'debug' -> 'debug_engine'
    config_attr_name = (
        f"{engine_name}_engine" if engine_name == "debug" else engine_name
    )

    # 从主配置中提取特定于该引擎的配置部分
    engine_config_data = getattr(config, config_attr_name, None)
    if engine_config_data is None:
        raise ConfigurationError(
            f"引擎 '{engine_name}' 的配置部分 (属性: {config_attr_name}) 在主配置中不存在。"
        )

    try:
        # 使用引擎类定义的 Pydantic 模型来验证和创建配置对象
        engine_config = engine_class.CONFIG_MODEL.model_validate(
            engine_config_data.model_dump()
        )
        engine_instance = engine_class(config=engine_config)
        logger.info("翻译引擎已成功创建", engine=engine_name)
        return engine_instance
    except Exception as e:
        raise ConfigurationError(
            f"创建引擎 '{engine_name}' 实例时配置验证失败: {e}"
        ) from e
