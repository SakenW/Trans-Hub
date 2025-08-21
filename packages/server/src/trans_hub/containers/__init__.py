# packages/server/src/trans_hub/containers/__init__.py
"""
[DI 重构] 应用的组合根 (Composition Root)。

本模块定义了 `ApplicationContainer`，它是所有 DI 容器的聚合点。
它负责装配所有子容器，并管理核心资源（如数据库连接池）的生命周期。
"""

from __future__ import annotations

from dependency_injector import containers, providers
from trans_hub.config import TransHubConfig

from .cache import CacheContainer
from .core import CoreContainer
from .engines import EnginesContainer
from .persistence import PersistenceContainer
from .services import ServicesContainer


class ApplicationContainer(containers.DeclarativeContainer):
    """应用的顶层 DI 容器，作为组合根。"""

    # --- 核心配置通道 ---
    # 1. 整块配置对象，作为唯一事实来源 (SSOT) 向下传递
    pydantic_config = providers.Dependency(instance_of=TransHubConfig)
    # 2. 字段级配置提供者，用于需要细粒度配置的场景 (如日志)
    config = providers.Configuration()

    # --- 子容器装配 ---
    core = providers.Container(
        CoreContainer,
        config=config,
    )
    persistence = providers.Container(
        PersistenceContainer,
        config=pydantic_config,
    )
    cache = providers.Container(
        CacheContainer,
        config=pydantic_config,
    )
    engines = providers.Container(
        EnginesContainer,
        config=pydantic_config,
    )
    services = providers.Container(
        ServicesContainer,
        config=pydantic_config,
        uow_factory=persistence.uow_factory,
        cache_handler=cache.cache_handler,
    )
