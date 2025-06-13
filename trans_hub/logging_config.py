"""trans_hub/logging_config.py (v1.0 Final)

集中配置项目的日志系统。
使用 structlog 实现结构化的、带上下文的日志记录。
此版本修复了 Mypy 报告的类型不兼容问题。
"""

import logging  # 标准 logging 模块
import sys
from typing import List, Literal, Union

import structlog
from structlog.dev import ConsoleRenderer

# 导入 structlog 的处理器和渲染器
from structlog.processors import JSONRenderer

# 导入 structlog 相关的类型，特别是 Processor
from structlog.typing import Processor

# 使用 contextvars 来安全地在异步和多线程环境中传递上下文
# 我们用它来传递 correlation_id
structlog.contextvars.bind_contextvars(correlation_id=None)


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
    """配置整个应用的日志系统。

    根据 `log_format` 参数决定使用开发环境友好的控制台格式或生产环境友好的 JSON 格式。

    Args:
    ----
        log_level: 日志级别，如 "DEBUG", "INFO", "WARNING" 等。不区分大小写。
        log_format: 日志输出格式。'console' 适用于开发环境，'json' 适用于生产环境。

    """
    # 定义 structlog 的基础处理器链（不包含最终渲染器）
    # 明确 `shared_processors` 的类型为 `List[Processor]`
    shared_processors: List[Processor] = [
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
        # 如果需要，可以添加更多 CallSiteParameterAdder
        # structlog.processors.CallsiteParameterAdder(
        #     [
        #         structlog.processors.CallsiteParameterAdder.FILENAME,
        #         structlog.processors.CallsiteParameterAdder.LINENO,
        #         structlog.processors.CallsiteParameterAdder.FUNC_NAME,
        #     ]
        # ),
    ]

    # 为 structlog 配置处理器链
    # 这些处理器会在日志事件字典被最终渲染之前依次执行
    structlog.configure(
        processors=shared_processors
        + [
            # 必须是最后一个 structlog 处理器：
            # 它将 structlog 处理后的事件字典转换为标准 logging.LogRecord
            # 并在 `ProcessorFormatter` 中被进一步处理。
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 为标准 logging 配置渲染器（最终输出格式）
    # 明确声明 `renderer` 变量的类型为 `Union`
    renderer: Union[JSONRenderer, ConsoleRenderer]
    if log_format == "json":
        # 生产环境推荐使用 JSON 格式，便于机器解析和日志聚合
        renderer = structlog.processors.JSONRenderer()
    else:
        # 开发环境使用控制台友好的彩色格式，便于人工阅读
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # 创建一个标准的 logging Formatter，但其内部使用 structlog 的渲染器
    formatter = structlog.stdlib.ProcessorFormatter(
        # `foreign_pre_chain` 用于处理那些不经过 structlog 管道，
        # 直接通过标准 logging 模块发出的日志记录（例如来自第三方库的日志）。
        # 这些日志在被 `ProcessorFormatter` 格式化之前，会先经过 `shared_processors` 处理。
        foreign_pre_chain=shared_processors,
        # `processor` 指定了最终如何渲染日志事件字典为字符串。
        processor=renderer,
    )

    # 创建并配置一个 StreamHandler，将日志输出到标准输出
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # 获取根 logger 并应用我们的配置
    # 注意：我们直接修改根 logger，这样所有通过 `logging.getLogger()` 获取的 logger
    # 都会继承这个配置（除非它们被独立配置过）。
    root_logger = logging.getLogger()
    # 清除任何可能存在的旧处理器，避免重复日志输出或配置冲突
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    # 设置日志级别，并转换为大写以确保兼容性
    root_logger.setLevel(log_level.upper())

    # 修复 F821 错误：直接使用标准 logging 模块发送此配置完成消息
    logging.info(f"日志系统已配置完成。级别: {log_level}, 格式: {log_format}")
