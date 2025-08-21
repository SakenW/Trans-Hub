# packages/server/src/trans_hub/containers/services.py
"""
[DI 重构] 应用服务层容器。

负责组装所有业务用例服务和总协调器 (Coordinator)。
本容器只依赖于抽象接口，不依赖任何具体的基础设施实现。
"""

from dependency_injector import containers, providers
from trans_hub.application import coordinator, resolvers, services
from trans_hub.config import TransHubConfig
from trans_hub_core.interfaces import CacheHandler
from trans_hub_core.uow import IUnitOfWork


class ServicesContainer(containers.DeclarativeContainer):
    """应用服务和协调器的容器。"""

    config = providers.Dependency(instance_of=TransHubConfig)
    uow_factory = providers.Dependency(instance_of=IUnitOfWork)
    cache_handler = providers.Dependency(instance_of=CacheHandler)

    # --- 解析器 ---
    translation_resolver = providers.Factory(
        resolvers.TranslationResolver,
        uow_factory=uow_factory,
    )

    # --- 原子应用服务 ---
    commenting_service = providers.Factory(
        services.CommentingService,
        uow_factory=uow_factory,
        config=config,
    )
    request_translation_service = providers.Factory(
        services.RequestTranslationService,
        uow_factory=uow_factory,
        config=config,
    )
    revision_lifecycle_service = providers.Factory(
        services.RevisionLifecycleService,
        uow_factory=uow_factory,
        config=config,
    )
    translation_query_service = providers.Factory(
        services.TranslationQueryService,
        uow_factory=uow_factory,
        config=config,
        cache=cache_handler,
        resolver=translation_resolver,
    )

    # --- 总协调器 (门面) ---
    coordinator = providers.Factory(
        coordinator.Coordinator,
        request_service=request_translation_service,
        lifecycle_service=revision_lifecycle_service,
        commenting_service=commenting_service,
        query_service=translation_query_service,
    )
