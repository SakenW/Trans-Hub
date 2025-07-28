# trans_hub/logging_config.py
"""
本模块负责集中配置项目的日志系统。

它使用 structlog 实现结构化的、上下文感知的日志记录，支持 JSON 和控制台两种输出格式。
此版本经过优化，可在控制台模式下启用“pretty exceptions”功能。
"""

import logging
import sys
from typing import Literal, Union

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.typing import Processor

# 使用 contextvars 来安全地在异步环境中传递上下文
structlog.contextvars.bind_contextvars(correlation_id=None)


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
    """
    配置整个应用的日志系统。

    此函数应在应用启动时尽早调用。

    参数:
        log_level: 日志级别 (例如 "INFO", "DEBUG")。
        log_format: 日志输出格式，'console' 适用于开发，'json' 适用于生产。
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # --- 核心修正：首先确定最终的渲染器 ---
    renderer: Union[JSONRenderer, ConsoleRenderer]
    if log_format == "json":
        # JSON 格式需要一个额外的处理器来将异常信息转换为字符串
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        # ConsoleRenderer 可以直接处理异常信息，实现 "pretty exceptions"
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # structlog 主日志记录器的配置
    structlog.configure(
        processors=shared_processors
        + [
            # 这个特殊的处理器为标准库 logging 的集成做准备
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 标准库 logging 的配置，用于捕获来自其他库的日志
    handler = logging.StreamHandler(sys.stdout)
    # --- 核心修正：为 ProcessorFormatter 提供最终的渲染器 ---
    # 这个 formatter 会将标准日志记录传递给 shared_processors，
    # 然后由我们指定的 renderer 进行最终渲染。
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=renderer,
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    s_logger = structlog.get_logger("trans_hub.logging_config")
    s_logger.info("日志系统已配置完成。", level=log_level.upper(), format=log_format)
