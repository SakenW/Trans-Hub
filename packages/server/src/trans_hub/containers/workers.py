# packages/server/src/trans_hub/containers/workers.py
"""
[DI 重构] 后台 Worker 容器。

负责提供后台工作进程的实例。
"""

from dependency_injector import containers, providers
from trans_hub.application.processors import TranslationProcessor
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.engines.base import BaseTranslationEngine
from trans_hub.infrastructure.uow import UowFactory
from trans_hub.workers._outbox_relay_worker import OutboxRelayWorker
from trans_hub.workers._translation_worker import TranslationWorker
from trans_hub_core.interfaces import StreamProducer


class WorkersContainer(containers.DeclarativeContainer):
    """后台 Worker 实例的容器。"""

    config = providers.Dependency(instance_of=TransHubConfig)
    uow_factory = providers.Dependency(instance_of=UowFactory)
    active_engine = providers.Dependency(instance_of=BaseTranslationEngine)
    stream_producer = providers.Dependency(instance_of=StreamProducer)

    # 翻译处理器是 TranslationWorker 的一个依赖
    translation_processor = providers.Factory(
        TranslationProcessor,
        stream_producer=stream_producer,
        event_stream_name=config.provided.worker.event_stream_name,
    )

    # 提供 TranslationWorker 的实例
    translation_worker = providers.Factory(
        TranslationWorker,
        config=config,
        uow_factory=uow_factory,
        processor=translation_processor,
        active_engine=active_engine,
    )

    # 提供 OutboxRelayWorker 的实例
    outbox_relay_worker = providers.Factory(
        OutboxRelayWorker,
        config=config,
        uow_factory=uow_factory,
        stream_producer=stream_producer,
    )
