"""trans_hub/logging_config.py

集中配置项目的日志系统。
使用 structlog 实现结构化的、带上下文的日志记录。
"""
import logging
import sys
from typing import Literal

import structlog

# 使用 contextvars 来安全地在异步和多线程环境中传递上下文
# 我们用它来传递 correlation_id
structlog.contextvars.bind_contextvars(correlation_id=None)


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
    """配置整个应用的日志系统。

    Args:
    ----
        log_level: 日志级别，如 "DEBUG", "INFO", "WARNING"。
        log_format: 日志输出格式。'console' 适用于开发环境，'json' 适用于生产环境。

    """
    # 共享的处理器，用于格式化和丰富日志记录
    shared_processors = [
        # 添加 structlog 的上下文信息到日志记录中
        structlog.contextvars.merge_contextvars,
        # 添加日志级别、时间戳等标准信息
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        # 将位置参数格式化到消息中 (e.g., logger.info("user %s logged in", username))
        structlog.stdlib.PositionalArgumentsFormatter(),
        # 将所有信息打包成一个事件字典
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # 为 structlog 配置处理器链
    # 这是 structlog 内部使用的，最终会传递给标准 logging
    structlog.configure(
        processors=shared_processors
        + [
            # 必须是最后一个 structlog 处理器
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 为标准 logging 配置渲染器（最终输出格式）
    if log_format == "json":
        # 生产环境推荐使用 JSON 格式，便于机器解析
        renderer = structlog.processors.JSONRenderer()
    else:
        # 开发环境使用控制台友好的彩色格式
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # 创建一个标准的 logging Formatter，但其内部使用 structlog 的渲染器
    formatter = structlog.stdlib.ProcessorFormatter(
        # `foreign_pre_chain` 用于处理非 structlog（例如来自其他库）的日志
        foreign_pre_chain=shared_processors,
        # `processor` 指定了最终如何渲染日志
        processor=renderer,
    )

    # 创建并配置一个 StreamHandler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # 获取根 logger 并应用我们的配置
    # 注意：我们直接修改根 logger，这样所有子 logger 都会继承这个配置
    root_logger = logging.getLogger()
    # 清除任何可能存在的旧处理器
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # 让所有子 logger (包括我们自己的和第三方库的) 都遵循这个配置
    logging.info(f"日志系统已配置完成。级别: {log_level}, 格式: {log_format}")
