# trans_hub/optimized_logging_config.py
"""
本模块负责集中配置项目的日志系统，并与 Rich 库集成以提供美观的、信息块式的控制台输出。
此版本采用自定义的智能混合渲染器，并进行了最终的美学与健壮性修复。
"""

import logging
from typing import TYPE_CHECKING, Any, List, Literal, MutableMapping

import structlog
from structlog.typing import Processor

if TYPE_CHECKING:
    from rich.console import Console, Group, RenderableType
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
else:
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
    一个智能的 structlog 处理器，根据日志的重要程度选择渲染风格，并进行了美学优化。
    """

    def __init__(
        self,
        kv_truncate_at: int = 80,
        show_timestamp: bool = True,
        show_logger_name: bool = True,
    ):
        self._console = Console()
        self._kv_truncate_at = kv_truncate_at
        self._show_timestamp = show_timestamp
        self._show_logger_name = show_logger_name

        # 定义日志级别的样式
        self._level_styles = {
            "debug": ("blue", "DEBUG    "),
            "info": ("green", "INFO     "),
            "warning": ("yellow", "WARNING  "),
            "error": ("bold red", "ERROR    "),
            "critical": ("bold magenta", "CRITICAL "),
        }

        # 定义哪些级别的日志应该渲染为面板
        self._panel_levels = {"warning", "error", "critical"}

    def __call__(
        self, logger: Any, name: str, event_dict: MutableMapping[str, Any]
    ) -> str:
        event = str(event_dict.pop("event", "")).strip()
        if not event:
            return ""

        # 提取日志属性
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").lower()
        logger_name = event_dict.pop("logger", "unknown")

        # 获取级别对应的样式
        style, level_text = self._level_styles.get(level, ("default", level.upper()))

        # 决定渲染方式
        if level in self._panel_levels or event_dict:
            return self._render_as_panel(
                timestamp, level_text, style, logger_name, event, event_dict
            )
        else:
            return self._render_as_line(
                timestamp, level_text, style, logger_name, event
            )

    def _render_as_panel(
        self,
        timestamp: str,
        level_text: str,
        border_style: str,
        logger_name: str,
        event: str,
        kv: MutableMapping[str, Any],
    ) -> str:
        """将日志渲染为面板样式"""
        # 构建面板标题
        title_parts = []
        if self._show_logger_name:
            title_parts.append(
                f"[{border_style}]{level_text}[/] [cyan dim]({logger_name})[/]"
            )
        else:
            title_parts.append(f"[{border_style}]{level_text}[/]")

        title = Text.from_markup(" ".join(title_parts))

        # 构建面板内容
        renderables: List["RenderableType"] = [Text(event)]

        # 添加键值对表格
        if kv:
            kv_table = Table(
                show_header=False, show_edge=False, box=None, padding=(0, 1)
            )
            kv_table.add_column(style="dim", width=20)
            kv_table.add_column(style="bright_white")

            # 按键名排序并添加到表格
            for key, value in sorted(kv.items()):
                value_repr = repr(value)
                # 对于长内容，保持完整显示并允许换行
                if len(value_repr) > self._kv_truncate_at:
                    # 移除 repr 的引号以更好地显示多行内容
                    if value_repr.startswith("'") and value_repr.endswith("'"):
                        value_repr = value_repr[1:-1]
                    elif value_repr.startswith('"') and value_repr.endswith('"'):
                        value_repr = value_repr[1:-1]
                    # 使用 Text 类处理长内容的换行
                    value_text = Text(value_repr, overflow="fold")
                    kv_table.add_row(f"  {key}", value_text)
                else:
                    kv_table.add_row(f"  {key}", value_repr)
            renderables.append(kv_table)

        render_group = Group(*renderables)

        # 添加时间戳作为面板副标题
        subtitle = None
        if self._show_timestamp and timestamp:
            subtitle = Text(str(timestamp), style="dim")

        # 渲染面板
        with self._console.capture() as capture:
            self._console.print(
                Panel(
                    render_group,
                    title=title,
                    border_style=border_style,
                    subtitle=subtitle,
                    subtitle_align="right",
                    expand=False,
                    # 允许内容换行以适应面板宽度
                    width=self._console.width,
                )
            )
        return capture.get().rstrip()

    def _render_as_line(
        self, timestamp: str, level_text: str, style: str, logger_name: str, event: str
    ) -> str:
        """将日志渲染为行样式"""
        line = Text()

        # 添加时间戳
        if self._show_timestamp:
            line.append(str(timestamp), style="dim")
            line.append(" ")

        # 添加级别
        line.append(level_text, style=style)
        line.append(" ")

        # 添加事件
        line.append(event)

        # 添加记录器名称
        if self._show_logger_name:
            line.append(" ")
            line.append(f"({logger_name})", style="cyan dim")

        # 渲染行
        with self._console.capture() as capture:
            self._console.print(line)
        return capture.get().rstrip()


def setup_logging(
    log_level: str = "INFO",
    log_format: Literal["json", "console"] = "console",
    show_timestamp: bool = True,
    show_logger_name: bool = True,
    kv_truncate_at: int = 80,
) -> None:
    """ ""
    配置日志系统。

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: 日志格式 (console 或 json)
        show_timestamp: 是否显示时间戳
        show_logger_name: 是否显示记录器名称
        kv_truncate_at: 键值对值的截断长度
    """
    # 检查Rich库是否可用
    if log_format == "console" and Console is None:
        raise ImportError(
            "要使用 'console' 日志格式，请安装 'rich' 库: pip install rich"
        )

    # 定义处理器链
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # 根据格式选择处理器
    if log_format == "console":
        # 使用优化的混合渲染器
        processors.append(
            HybridPanelRenderer(
                kv_truncate_at=kv_truncate_at,
                show_timestamp=show_timestamp,
                show_logger_name=show_logger_name,
            )
        )
    else:
        # JSON格式使用ISO时间戳
        processors[3] = structlog.processors.TimeStamper(fmt="iso", utc=True)
        processors.append(structlog.processors.JSONRenderer())

    # 配置structlog
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 配置标准库日志记录器
    handler = logging.StreamHandler()

    class PassthroughFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return str(record.getMessage())

    handler.setFormatter(PassthroughFormatter())

    # 配置根记录器
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)

    # 配置应用记录器
    app_logger = logging.getLogger("trans_hub")
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = True

    # 记录日志系统配置完成
    s_logger = structlog.get_logger("trans_hub.logging_config")
    s_logger.info(
        "日志系统已配置完成。", log_format=log_format, app_log_level=log_level.upper()
    )
