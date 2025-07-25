# trans_hub/logging_config.py (终极完美版)
"""
集中配置项目的日志系统。
使用 structlog 实现结构化的、带上下文的日志记录。
"""

import logging
import sys
from typing import Literal, Union

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer

# --- 核心修正：导入 Processor 类型以进行精确注解 ---
from structlog.typing import Processor

# 使用 contextvars 来安全地在异步环境中传递上下文
structlog.contextvars.bind_contextvars(correlation_id=None)


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
    """
    配置整个应用的日志系统。

    根据 `log_format` 决定使用开发环境友好的控制台格式或生产环境友好的 JSON 格式。
    """
    # --- 核心修正：为 shared_processors 添加显式类型注解，帮助 Mypy 理解 ---
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # --- 核心修正：为 renderer 添加显式 Union 类型注解 ---
    renderer: Union[JSONRenderer, ConsoleRenderer]
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    handler = logging.StreamHandler(sys.stdout)
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=renderer,
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    logging.info(f"日志系统已配置完成。级别: {log_level.upper()}, 格式: {log_format}")
