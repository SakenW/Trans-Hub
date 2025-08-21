# packages/server/src/trans_hub/containers/core.py
"""
[DI 重构] 核心容器。

负责提供应用范围内的基础服务和配置，如日志、时钟、ID 生成器等。
它主要使用字段级的配置提供者。
"""

from dependency_injector import containers, providers
from trans_hub.observability.logging_config import setup_logging


class CoreContainer(containers.DeclarativeContainer):
    """核心服务和配置的容器。"""

    config = providers.Configuration()

    # 日志系统初始化器
    # 它是一个 Effect provider，在 wiring 时被调用一次以配置全局日志
    logging = providers.Resource(
        setup_logging,
        log_level=config.logging.level,
        log_format=config.logging.format,
        service=config.service_name,
    )
