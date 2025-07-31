# trans_hub/logging_config.py
"""
本模块负责集中配置项目的日志系统，并与 Rich 库集成以提供美观的、信息块式的控制台输出。
此版本采用自定义的智能混合渲染器，是经过多轮迭代后的最终、稳定版本。
"""

# 1. 标准库导入
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Literal, MutableMapping, TYPE_CHECKING

# 2. 第三方库导入
import structlog
from structlog.typing import Processor

# 3. 类型检查时的导入 (处理可选依赖的最佳实践)
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
        # 在运行时，我们不需要精确的 RenderableType，Any 即可
        RenderableType = Any
    except ImportError:
        # 如果 rich 未安装，将所有相关类设为 None
        Console, Group, Panel, Table, Text, RenderableType = (None,) * 6


class HybridPanelRenderer:
    """
    一个智能的 structlog 处理器，根据日志的重要程度选择渲染风格，并进行了美学优化。
    - 对 WARNING 及以上级别，或带有附加上下文的日志，使用 Panel。
    - 对简单的 INFO/DEBUG 日志，使用紧凑的单行格式。
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

    def __call__(self, logger: Any, name: str, event_dict: MutableMapping[str, Any]) -> str:
        # 健壮性处理：清理主消息，如果为空则不渲染
        event = str(event_dict.pop("event", "")).strip()
        if not event:
            return ""
            
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").upper()
        logger_name = event_dict.pop("logger", "unknown")
        border_style, level_text = self._level_styles.get(level, ("default", level))

        # 智能渲染决策
        if level in ("WARNING", "ERROR", "CRITICAL") or event_dict:
            return self._render_as_panel(timestamp, level_text, border_style, logger_name, event, event_dict)
        else:
            return self._render_as_line(timestamp, level_text, border_style, logger_name, event)

    def _render_as_panel(self, timestamp: str, level_text: str, border_style: str, logger_name: str, event: str, kv: MutableMapping[str, Any]) -> str:
        title = Text.from_markup(f"[{border_style}]{level_text}[/] [cyan dim]({logger_name})[/]")
        renderables: List["RenderableType"] = [Text(event)]
        if kv:
            kv_table = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
            kv_table.add_column(style="dim", width=20)
            kv_table.add_column(style="bright_white")
            for key, value in sorted(kv.items()):
                # 智能截断长内容
                value_repr = repr(value)
                if len(value_repr) > self._kv_truncate_at:
                    value_repr = value_repr[:self._kv_truncate_at] + "..."
                kv_table.add_row(f"  {key}", value_repr)
            renderables.append(kv_table)
        
        # 使用 Group 组合不同类型的 Rich 对象
        render_group = Group(*renderables)

        with self._console.capture() as capture:
            self._console.print(Panel(render_group, title=title, border_style=border_style, subtitle=Text(str(timestamp), style="dim"), subtitle_align="right", expand=False))
        return capture.get().rstrip()

    def _render_as_line(self, timestamp: str, level_text: str, style: str, logger_name: str, event: str) -> str:
        line = Text()
        line.append(str(timestamp), style="dim")
        line.append(" ")
        line.append(level_text, style=style)
        line.append(" ")
        line.append(event)
        line.append(" ",)
        line.append(f"({logger_name})", style="cyan dim")
        with self._console.capture() as capture:
            self._console.print(line)
        return capture.get().rstrip()


def setup_logging(
    log_level: str = "INFO", log_format: Literal["json", "console"] = "console"
) -> None:
    if log_format == "console" and Console is None:
        raise ImportError("要使用 'console' 日志格式，请安装 'rich' 库: pip install rich")

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
    
    # 精确控制日志级别
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING) # 过滤第三方库

    app_logger = logging.getLogger("trans_hub")
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = True

    s_logger = structlog.get_logger("trans_hub.logging_config")
    s_logger.info("日志系统已配置完成。", log_format=log_format, app_log_level=log_level.upper())