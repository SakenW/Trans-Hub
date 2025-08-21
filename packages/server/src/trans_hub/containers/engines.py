# packages/server/src/trans_hub/containers/engines.py
"""
[DI 重构] 翻译引擎容器。

负责实例化和提供当前激活的翻译引擎。
"""

from dependency_injector import containers, providers
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.engines.base import BaseTranslationEngine
from trans_hub.infrastructure.engines.factory import create_engine_instance


class EnginesContainer(containers.DeclarativeContainer):
    """翻译引擎相关服务的容器。"""

    config = providers.Dependency(instance_of=TransHubConfig)

    # 激活的翻译引擎实例是一个工厂，它在首次被需要时
    # 根据配置动态创建
    active_engine: providers.Factory[BaseTranslationEngine] = providers.Factory(
        create_engine_instance,
        config=config,
        engine_name=config.provided.active_engine,
    )
