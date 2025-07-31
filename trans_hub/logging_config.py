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
    """

    def __init__(self, kv_truncate_at: int = 80):
        self._console = Console()
        self._kv_truncate_at = kv_truncate_at
        self._level_styles = {
            "INFO": ("green", "INFO     "),
            "WARNING": ("yellow", "WARNING  "),
            "ERROR": ("bold red", "ERROR    "),
            "CRITICAL": ("bold magenta", "CRITICAL "),
            "DEBUG": ("blue", "DEBUG    "),
        }

    def __call__(
        self, logger: Any, name: str, event_dict: MutableMapping[str, Any]
    ) -> str:
        event = str(event_dict.pop("event", "")).strip()
        if not event:
            return ""

        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").upper()
        logger_name = event_dict.pop("logger", "unknown")

        border_style, level_text = self._level_styles.get(level, ("default", level))

        if level in ("WARNING", "ERROR", "CRITICAL") or event_dict:
            return self._render_as_panel(
                timestamp, level_text, border_style, logger_name, event, event_dict
            )
        else:
            return self._render_as_line(
                timestamp, level_text, border_style, logger_name, event
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
        title = Text.from_markup(
            f"[{border_style}]{level_text}[/] [cyan dim]({logger_name})[/]"
        )
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
                    value_repr = value_repr[: self._kv_truncate_at] + "..."
                kv_table.add_row(f"  {key}", value_repr)
            renderables.append(kv_table)

        render_group = Group(*renderables)

        with self._console.capture() as capture:
            self._console.print(
                Panel(
                    render_group,
                    title=title,
                    border_style=border_style,
                    subtitle=Text(str(timestamp), style="dim"),
                    subtitle_align="right",
                    expand=False,
                )
            )
        return capture.get().rstrip()

    def _render_as_line(
        self, timestamp: str, level_text: str, style: str, logger_name: str, event: str
    ) -> str:
        line = Text()
        line.append(str(timestamp), style="dim")
        line.append(" ")
        line.append(level_text, style=style)
        line.append(" ")
        line.append(event)
        line.append(
            " ",
        )
        line.append(f"({logger_name})", style="cyan dim")

        with self._console.capture() as capture:
            self._console.print(line)
        return capture.get().rstrip()


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
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
        processors.append(HybridPanelRenderer())
    else:
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
