# trans_hub/logging_config.py
"""
本模块负责集中配置项目的日志系统，并与 Rich 库集成以提供美观的、信息块式的控制台输出。
此版本采用自定义的智能混合渲染器，并进行了最终的美学与健壮性修复。
"""

import logging
from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any, Literal  # <-- [核心修复] 移除了不再需要的 cast

import structlog
from structlog.typing import Processor

# 为了支持可选依赖和静态类型检查，我们使用 TYPE_CHECKING 块。
# 这样，只有在 mypy 运行时才会真正导入这些类型，
# 如果用户没有安装 'rich'，项目仍然可以正常运行而不会引发 ImportError。
if TYPE_CHECKING:
    from rich.console import Console, Group, RenderableType
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
else:
    # 在实际运行时，我们尝试导入 rich。
    # 如果失败，将这些名称设置为 None，并在 setup_logging 中进行检查。
    try:
        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        RenderableType = Any
    except ImportError:
        Console, Group, Panel, Table, Text, RenderableType = (None,) * 6


class HybridPanelRenderer:
    """
    一个智能的 structlog 处理器，它将日志渲染为具有完美对齐的、高度可读的面板样式。
    它旨在提供比标准行式日志更丰富的上下文和更佳的可读性。
    """

    def __init__(
        self,
        log_level: str = "INFO",
        kv_truncate_at: int = 256,
        show_timestamp: bool = True,
        show_logger_name: bool = True,
        kv_key_width: int = 15,
    ):
        """
        初始化渲染器。

        Args:
            log_level: 应用的全局日志级别，用于决定哪些日志需要高亮。
            kv_truncate_at: 键值对中值的最大显示长度，超长则会折叠。
            show_timestamp: 是否在面板右下角显示时间戳。
            show_logger_name: 是否在面板标题中显示日志记录器的名称。
            kv_key_width: 键值对表格中“键”列的固定宽度，用于实现完美的垂直对齐。

        """
        if Console is None:
            raise ImportError("要使用 HybridPanelRenderer, 请安装 'rich' 库。")
        self._console = Console()
        self._log_level = log_level.upper()
        self._kv_truncate_at = kv_truncate_at
        self._show_timestamp = show_timestamp
        self._show_logger_name = show_logger_name
        self._kv_key_width = kv_key_width
        self._is_first_render = True

        # 定义每个日志级别的颜色和文本表示，确保长度一致以实现对齐。
        self._level_styles = {
            "debug": ("blue", "DEBUG   "),
            "info": ("green", "INFO    "),
            "warning": ("yellow", "WARNING "),
            "error": ("bold red", "ERROR   "),
            "critical": ("bold magenta", "CRITICAL"),
        }
        self._panel_levels = {"info", "warning", "error", "critical"}

    def __call__(
        self, logger: Any, name: str, event_dict: MutableMapping[str, Any]
    ) -> str:
        """
        Structlog 处理器的主调用方法。
        它接收原始日志字典，将其渲染为字符串，然后返回。
        """
        # 从日志字典中提取核心信息。'event' 是主消息。
        event = str(event_dict.pop("event", "")).strip()
        if not event:
            return ""  # 如果没有消息，则不输出任何内容。

        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").lower()
        logger_name = event_dict.pop("logger", "unknown")
        style, level_text = self._level_styles.get(level, ("default", level.upper()))

        # 决定是渲染为面板还是简单的行。目前总是渲染为面板。
        rendered_output = self._render_as_panel(
            timestamp, level_text, style, logger_name, event, event_dict
        )

        # 为了美观，在第一次输出日志前打印一个换行符。
        if self._is_first_render and rendered_output:
            self._is_first_render = False
            return f"\n{rendered_output}"

        return rendered_output

    def _render_as_panel(
        self,
        timestamp: str,
        level_text: str,
        border_style: str,
        logger_name: str,
        event: str,
        kv: MutableMapping[str, Any],
    ) -> str:
        """将日志渲染为具有完美对齐的、高度可读的 Rich Panel。"""
        # 构建面板标题，包含日志级别和记录器名称。
        title_parts = [f"[{border_style}]{level_text}[/]"]
        if self._show_logger_name:
            title_parts.append(f"[cyan dim]({logger_name})[/]")
        title = Text.from_markup(" ".join(title_parts))

        # 面板的主要内容从主消息开始。
        renderables: list[RenderableType] = [Text(event, justify="left")]

        # 如果有键值对（附加上下文信息），则创建一个表格来格式化它们。
        if kv:
            # 使用固定宽度键列的表格来实现完美的垂直对齐。
            kv_table = Table(
                show_header=False, show_edge=False, box=None, padding=(0, 1)
            )
            kv_table.add_column(style="dim", justify="right", width=self._kv_key_width)
            kv_table.add_column(style="bright_white", overflow="fold")

            for key, value in sorted(kv.items()):
                value_repr = repr(value)
                # 对长字符串进行特殊处理，移除引号以获得更好的换行效果。
                if len(value_repr) > self._kv_truncate_at or "\n" in value_repr:
                    if value_repr.startswith("'") and value_repr.endswith("'"):
                        value_repr = value_repr[1:-1]
                    elif value_repr.startswith('"') and value_repr.endswith('"'):
                        value_repr = value_repr[1:-1]
                kv_table.add_row(f"{key} :", Text(value_repr))

            renderables.append(kv_table)

        # 将主消息和键值对表格组合在一起。
        render_group = Group(*renderables)

        # 创建右下角的副标题（时间戳）。
        subtitle = (
            Text(str(timestamp), style="dim")
            if self._show_timestamp and timestamp
            else None
        )

        # 使用 Rich Console 的 capture 功能将 Panel 对象渲染为字符串。
        with self._console.capture() as capture:
            self._console.print(
                Panel(
                    render_group,
                    title=title,
                    border_style=border_style,
                    subtitle=subtitle,
                    subtitle_align="right",
                    expand=False,
                    title_align="left",
                )
            )

        # [核心修复] 移除多余的 cast。
        # 在 mypy.overrides 中忽略 rich 后，mypy 不再抱怨此处的类型问题。
        return capture.get().rstrip()

    def _render_as_line(
        self, timestamp: str, level_text: str, style: str, logger_name: str, event: str
    ) -> str:
        """将日志渲染为简单的单行文本（备用）。"""
        line = Text()
        if self._show_timestamp:
            line.append(str(timestamp), style="dim")
            line.append(" ")
        line.append(level_text, style=style)
        line.append(" ")
        line.append(event)
        if self._show_logger_name:
            line.append(" ")
            line.append(f"({logger_name})", style="cyan dim")

        with self._console.capture() as capture:
            self._console.print(line)

        # [核心修复] 移除多余的 cast。
        return capture.get().rstrip()


def setup_logging(
    log_level: str = "INFO",
    log_format: Literal["json", "console"] = "console",
    show_timestamp: bool = True,
    show_logger_name: bool = True,
    kv_truncate_at: int = 80,
) -> None:
    """
    配置全局的 structlog 日志系统。这是整个应用的日志配置入口。

    Args:
        log_level: 要显示的最低日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)。
        log_format: 日志输出格式。'console' 用于开发环境的美观输出，'json' 用于生产环境的机器可读输出。
        show_timestamp: 是否在日志中包含时间戳。
        show_logger_name: 是否在日志中包含记录器的名称 (例如 'trans_hub.coordinator')。
        kv_truncate_at: 在 console 模式下，键值对中值的截断长度。

    """
    if log_format == "console" and Console is None:
        raise ImportError(
            "要使用 'console' 日志格式，请安装 'rich' 库: pip install rich"
        )

    # 定义 structlog 的处理器链。日志记录会依次通过这些处理器。
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # 1. 合并上下文变量
        structlog.stdlib.add_logger_name,  # 2. 添加记录器名称
        structlog.stdlib.add_log_level,  # 3. 添加日志级别
        structlog.processors.TimeStamper(
            fmt="%Y-%m-%d %H:%M:%S", utc=False
        ),  # 4. 添加时间戳
        structlog.stdlib.PositionalArgumentsFormatter(),  # 5. 格式化位置参数
        structlog.processors.StackInfoRenderer(),  # 6. 渲染堆栈信息
        structlog.processors.format_exc_info,  # 7. 格式化异常信息
    ]

    # 根据配置选择最终的渲染器。
    if log_format == "console":
        # 8a. 使用我们自定义的 Rich 面板渲染器。
        processors.append(
            HybridPanelRenderer(
                log_level=log_level,
                kv_truncate_at=kv_truncate_at,
                show_timestamp=show_timestamp,
                show_logger_name=show_logger_name,
            )
        )
    else:
        # 8b. 使用标准的 JSON 渲染器，并切换为 ISO 格式的时间戳。
        processors[3] = structlog.processors.TimeStamper(fmt="iso", utc=True)
        processors.append(structlog.processors.JSONRenderer())

    # 配置 structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 配置 Python 的标准 logging 库，使其成为 structlog 的输出端点。
    handler = logging.StreamHandler()

    class PassthroughFormatter(logging.Formatter):
        """一个简单的格式化器，直接传递 structlog 已经处理好的字符串。"""

        def format(self, record: logging.LogRecord) -> str:
            return str(record.getMessage())

    handler.setFormatter(PassthroughFormatter())

    # 清理并设置根记录器。
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)  # 根记录器级别较高，避免第三方库的噪音

    # 为我们的应用设置更低的日志级别。
    app_logger = logging.getLogger("trans_hub")
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = True  # 允许日志向上传播到根记录器

    # 打印一条日志，确认配置已完成。
    s_logger = structlog.get_logger("trans_hub.logging_config")
    if log_level.upper() == "DEBUG":
        print(
            f"DEBUG: 日志系统已配置完成。"
            f"log_format={log_format}, app_log_level={log_level.upper()}"
        )
    else:
        s_logger.info(
            "日志系统已配置完成。",
            log_format=log_format,
            app_log_level=log_level.upper(),
        )
