# packages/server/src/trans_hub/containers/persistence.py
"""
[DI 重构] 持久化层容器。

负责管理数据库连接、会话和仓库的生命周期。
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
)
from trans_hub.infrastructure.persistence import repositories
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork
from trans_hub_core import uow as uow_interfaces


class PersistenceContainer(containers.DeclarativeContainer):
    """持久化层相关服务的容器。"""

    config = providers.Dependency(instance_of=TransHubConfig)

    # 数据库引擎是一个异步资源，由容器管理其生命周期
    db_engine: providers.Resource[AsyncEngine] = providers.Resource(
        create_async_db_engine,
        cfg=config,
    )

    # Session Maker 是一个单例，依赖于已初始化的引擎
    session_maker: providers.Singleton[async_sessionmaker[AsyncSession]] = (
        providers.Singleton(
            create_async_sessionmaker,
            engine=db_engine,
        )
    )

    # UoW 是一个工厂，每次调用都会创建一个新的实例
    uow_factory: providers.Factory[uow_interfaces.IUnitOfWork] = providers.Factory(
        SqlAlchemyUnitOfWork,
        sessionmaker=session_maker,
    )

    # --- 仓库绑定 ---
    # 将具体的仓库实现绑定到核心契约包中定义的接口
    content_repo = providers.Factory(
        repositories.SqlAlchemyContentRepository,
        session=session_maker,
    )
    translation_repo = providers.Factory(
        repositories.SqlAlchemyTranslationRepository,
        session=session_maker,
    )
    tm_repo = providers.Factory(
        repositories.SqlAlchemyTmRepository,
        session=session_maker,
    )
    misc_repo = providers.Factory(
        repositories.SqlAlchemyMiscRepository,
        session=session_maker,
    )
    outbox_repo = providers.Factory(
        repositories.SqlAlchemyOutboxRepository,
        session=session_maker,
    )
