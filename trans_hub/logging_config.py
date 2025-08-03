# trans_hub/logging_config.py
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

    v3.1 最终修复：添加了首次渲染时自动换行的逻辑，以确保在任何环境下
    （如 pytest collecting 阶段）都能正确显示。
    """

    def __init__(
        self,
        kv_truncate_at: int = 80,
        show_timestamp: bool = True,
        show_logger_name: bool = True,
    ):
        """初始化渲染器。"""
        self._console = Console()
        self._kv_truncate_at = kv_truncate_at
        self._show_timestamp = show_timestamp
        self._show_logger_name = show_logger_name
        self._is_first_render = True

        # 定义日志级别的样式
        self._level_styles = {
            "debug": ("blue", "DEBUG    "),
            "info": ("green", "INFO     "),
            "warning": ("yellow", "WARNING  "),
            "error": ("bold red", "ERROR    "),
            "critical": ("bold magenta", "CRITICAL "),
        }
        self._panel_levels = {"warning", "error", "critical"}

    def __call__(
        self, logger: Any, name: str, event_dict: MutableMapping[str, Any]
    ) -> str:
        """structlog 处理器的主调用方法。"""
        event = str(event_dict.pop("event", "")).strip()
        if not event:
            return ""

        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").lower()
        logger_name = event_dict.pop("logger", "unknown")
        style, level_text = self._level_styles.get(level, ("default", level.upper()))

        if level in self._panel_levels or event_dict:
            rendered_output = self._render_as_panel(
                timestamp, level_text, style, logger_name, event, event_dict
            )
        else:
            rendered_output = self._render_as_line(
                timestamp, level_text, style, logger_name, event
            )

        if self._is_first_render and rendered_output:
            self._is_first_render = False
            # 确保首次渲染时输出从新的一行开始
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
        """将日志渲染为面板样式。"""
        title_parts = []
        if self._show_logger_name:
            title_parts.append(
                f"[{border_style}]{level_text}[/] [cyan dim]({logger_name})[/]"
            )
        else:
            title_parts.append(f"[{border_style}]{level_text}[/]")
        title = Text.from_markup(" ".join(title_parts))

        renderables: List["RenderableType"] = [Text(event)]
        if kv:
            kv_table = Table(
                show_header=False, show_edge=False, box=None, padding=(0, 1)
            )
            kv_table.add_column(style="dim", width=20)
            kv_table.add_column(style="bright_white")
            for key, value in sorted(kv.items()):
                value_repr = repr(value)
                if len(value_repr) > self._kv_truncate_at:
                    if value_repr.startswith("'") and value_repr.endswith("'"):
                        value_repr = value_repr[1:-1]
                    elif value_repr.startswith('"') and value_repr.endswith('"'):
                        value_repr = value_repr[1:-1]
                    value_text = Text(value_repr, overflow="fold")
                    kv_table.add_row(f"  {key}", value_text)
                else:
                    kv_table.add_row(f"  {key}", value_repr)
            renderables.append(kv_table)
        render_group = Group(*renderables)

        subtitle = None
        if self._show_timestamp and timestamp:
            subtitle = Text(str(timestamp), style="dim")

        with self._console.capture() as capture:
            self._console.print(
                Panel(
                    render_group,
                    title=title,
                    border_style=border_style,
                    subtitle=subtitle,
                    subtitle_align="right",
                    expand=False,
                    width=self._console.width,
                )
            )
        return capture.get().rstrip()

    def _render_as_line(
        self, timestamp: str, level_text: str, style: str, logger_name: str, event: str
    ) -> str:
        """将日志渲染为行样式。"""
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
        return capture.get().rstrip()


def setup_logging(
    log_level: str = "INFO",
    log_format: Literal["json", "console"] = "console",
    show_timestamp: bool = True,
    show_logger_name: bool = True,
    kv_truncate_at: int = 80,
) -> None:
    """
    配置日志系统。

    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: 日志格式 (console 或 json)
        show_timestamp: 是否显示时间戳
        show_logger_name: 是否显示记录器名称
        kv_truncate_at: 键值对值的截断长度
    """
    if log_format == "console" and Console is None:
        raise ImportError(
            "要使用 'console' 日志格式，请安装 'rich' 库: pip install rich"
        )

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "console":
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

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()

    class PassthroughFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            return str(record.getMessage())

    handler.setFormatter(PassthroughFormatter())

    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)

    app_logger = logging.getLogger("trans_hub")
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = True

    s_logger = structlog.get_logger("trans_hub.logging_config")
    s_logger.info(
        "日志系统已配置完成。", log_format=log_format, app_log_level=log_level.upper()
    )
