# packages/server/src/trans_hub/di/container.py
"""
应用依赖注入 (DI) 容器。

本模块使用 `dependency-injector` 库来定义和装配应用的所有核心组件，
包括配置、数据库连接、UoW、应用服务和适配器。
这是实现控制反转 (IoC) 和维护清晰架构的核心。
"""

from dependency_injector import containers, providers
from trans_hub.adapters.engines.factory import create_engine_instance
from trans_hub.application.coordinator import Coordinator
from trans_hub.application.processors import TranslationProcessor
from trans_hub.application.resolvers import TranslationResolver
from trans_hub.application.services import (
    CommentingService,
    EventPublisher,
    RequestTranslationService,
    RevisionLifecycleService,
    TranslationQueryService,
)
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
)
from trans_hub.infrastructure.redis._client import get_redis_client
from trans_hub.infrastructure.redis.cache import RedisCacheHandler
from trans_hub.infrastructure.redis.streams import RedisStreamProducer
from trans_hub.infrastructure.cache.memory import MemoryCacheHandler
from trans_hub_core.interfaces import CacheHandler
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork


class AppContainer(containers.DeclarativeContainer):
    """
    Trans-Hub 应用的核心 DI 容器。
    """

    # ==================================================================
    # 核心提供者 (Core Providers)
    # ==================================================================

    config = providers.Singleton(TransHubConfig)

    db_engine = providers.Singleton(create_async_db_engine, cfg=config)

    db_sessionmaker = providers.Singleton(create_async_sessionmaker, engine=db_engine)

    uow_factory = providers.Factory(
        SqlAlchemyUnitOfWork,
        sessionmaker=db_sessionmaker,
    )

    # ==================================================================
    # 可选基础设施 (Optional Infrastructure)
    # ==================================================================

    redis_client = providers.Resource(get_redis_client, config=config)

    # 简化缓存处理器配置，直接使用内存缓存避免 Redis 依赖问题
    cache_handler = providers.Singleton(
        MemoryCacheHandler,
        key_prefix=config.provided.redis.key_prefix,
    )

    stream_producer = providers.Singleton(RedisStreamProducer, client=redis_client)

    # ==================================================================
    # 适配器 (Adapters)
    # ==================================================================

    active_engine = providers.Singleton(
        create_engine_instance,
        config=config,
        engine_name=config.provided.active_engine,
    )

    # ==================================================================
    # 应用服务 (Application Services)
    # ==================================================================

    event_publisher = providers.Factory(
        EventPublisher,
        config=config,
    )

    translation_resolver = providers.Factory(
        TranslationResolver,
        uow_factory=uow_factory.provider,
    )

    translation_processor = providers.Factory(
        TranslationProcessor,
        uow_factory=uow_factory.provider,
        engine=active_engine,
        event_publisher=event_publisher,
    )

    request_translation_service = providers.Factory(
        RequestTranslationService,
        uow_factory=uow_factory.provider,
        config=config,
    )

    revision_lifecycle_service = providers.Factory(
        RevisionLifecycleService,
        uow_factory=uow_factory.provider,
        config=config,
    )

    commenting_service = providers.Factory(
        CommentingService,
        uow_factory=uow_factory.provider,
        event_publisher=event_publisher,
    )

    translation_query_service = providers.Factory(
        TranslationQueryService,
        uow_factory=uow_factory.provider,
        config=config,
        cache=cache_handler,
        resolver=translation_resolver,
    )

    # ==================================================================
    # 顶层门面 (Top-Level Facade)
    # ==================================================================

    coordinator = providers.Factory(
        Coordinator,
        request_service=request_translation_service,
        lifecycle_service=revision_lifecycle_service,
        commenting_service=commenting_service,
        query_service=translation_query_service,
    )
