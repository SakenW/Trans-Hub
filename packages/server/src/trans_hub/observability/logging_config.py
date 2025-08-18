# packages/server/src/trans_hub/observability/logging_config.py
"""
集中配置项目日志系统：structlog ⇄ 标准 logging，并与 Rich 深度集成。

提供两种输出：
- console：开发环境的面板式人类友好输出（本地时间，配色/对齐/长值折行）。
- json   ：生产环境的结构化日志（ISO-8601 且 UTC），便于日志平台聚合。

要点：
1) 使用 structlog 官方推荐的 ProcessorFormatter 桥接到标准 logging；
2) 自定义 HybridPanelRenderer 实现完美对齐、长值折行与首行空行；
3) console 用本地时间，json 统一 UTC；
4) 新增 setup_logging_from_config(cfg, service=...) 一步到位；
5) 可选屏蔽第三方噪声 logger（urllib3/sqlalchemy.engine 等）。
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any, Literal

import structlog
from structlog.typing import Processor

# ----------------------------
# 可选依赖：rich（软依赖处理）
# ----------------------------
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

        # 运行期可用时，类型保持原样；为兼容性，这里把 RenderableType 设为 Any
        RenderableType = Any  # 避免严格类型检查器在运行期报错
    except ImportError:
        Console, Group, Panel, Table, Text, RenderableType = (None,) * 6


class HybridPanelRenderer:
    """
    structlog 处理器：将日志渲染为 Rich 面板。

    设计目标：
    - 标题等宽级别标签（保证对齐）；
    - 值的长文本可折行显示（去引号改善折行）；
    - 首次打印前插入换行，避免与上文粘连；
    - 可配置是否显示时间戳与 logger 名称、键列宽度与截断长度。
    """

    def __init__(
        self,
        *,
        log_level: str = "INFO",
        kv_truncate_at: int = 256,
        show_timestamp: bool = True,
        show_logger_name: bool = True,
        kv_key_width: int = 15,
        panel_padding: tuple[int, int] = (1, 2),
    ) -> None:
        if Console is None:
            raise ImportError(
                "要使用 HybridPanelRenderer，请先安装 rich：\n"
                "  poetry add rich --group dev\n"
                "或：pip install rich"
            )
        self._console = Console()
        self._log_level = log_level.upper()
        self._kv_truncate_at = kv_truncate_at
        self._show_timestamp = show_timestamp
        self._show_logger_name = show_logger_name
        self._kv_key_width = kv_key_width
        self._panel_padding = panel_padding
        self._is_first_render = True

        # 等宽级别标签，保证标题对齐；配色可按团队偏好调整
        self._level_styles: dict[str, tuple[str, str]] = {
            "debug": ("cyan", "DEBUG   "),
            "info": ("green", "INFO    "),
            "warning": ("yellow", "WARNING "),
            "error": ("bold red", "ERROR   "),
            "critical": ("magenta", "CRITICAL"),
        }

    def __call__(
        self, logger: Any, name: str, event_dict: MutableMapping[str, Any]
    ) -> str:
        # 提取核心字段
        event_msg = str(event_dict.pop("event", "")).strip()
        if not event_msg:
            return ""  # 无消息不输出

        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "info").lower()
        logger_name = event_dict.pop("logger", "unknown")

        # 清理 structlog 注入但我们不直接展示的内部字段
        event_dict.pop("_record", None)
        event_dict.pop("_logger", None)

        border_style, level_text = self._level_styles.get(level, ("dim", level.upper()))

        rendered_output = self._render_as_panel(
            timestamp=timestamp,
            level_text=level_text,
            border_style=border_style,
            logger_name=logger_name,
            event=event_msg,
            kv=event_dict,
        )

        if self._is_first_render and rendered_output:
            self._is_first_render = False
            return f"\n{rendered_output}"
        return rendered_output

    def _render_as_panel(
        self,
        *,
        timestamp: str,
        level_text: str,
        border_style: str,
        logger_name: str,
        event: str,
        kv: MutableMapping[str, Any],
    ) -> str:
        # 标题：级别 + 可选 logger 名称
        title_parts = [f"[{border_style}]{level_text}[/]"]
        if self._show_logger_name:
            title_parts.append(f"[cyan dim]({logger_name})[/]")
        title = Text.from_markup(" ".join(title_parts))

        # 主消息
        renderables: list[RenderableType] = [Text(event, justify="left")]

        # 附加键值对：固定宽度键列 + 值折行；对超长字符串去引号以提升折行效果
        if kv:
            kv_table = Table(
                show_header=False, show_edge=False, box=None, padding=(0, 1)
            )
            kv_table.add_column(style="dim", justify="right", width=self._kv_key_width)
            kv_table.add_column(style="bright_white", overflow="fold")

            for key, value in sorted(kv.items()):
                value_repr = repr(value)
                if len(value_repr) > self._kv_truncate_at or "\n" in value_repr:
                    if value_repr.startswith("'") and value_repr.endswith("'"):
                        value_repr = value_repr[1:-1]
                    elif value_repr.startswith('"') and value_repr.endswith('"'):
                        value_repr = value_repr[1:-1]
                kv_table.add_row(f"{key} :", Text(value_repr))
            renderables.append(kv_table)

        render_group = Group(*renderables)

        subtitle = (
            Text(str(timestamp), style="dim")
            if (self._show_timestamp and timestamp)
            else None
        )

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
                    padding=self._panel_padding,
                )
            )
        return capture.get().rstrip()


def setup_logging(
    *,
    log_level: str = "INFO",
    log_format: Literal["json", "console"] = "console",
    tui_log_queue: asyncio.Queue[dict[str, Any]] | None = None, # [新增] TUI 队列
    show_timestamp: bool = True,
    show_logger_name: bool = True,
    kv_truncate_at: int = 256,
    kv_key_width: int = 15,
    root_level: str | None = None,
    service: str | None = None,
    silence_noisy_libs: bool = True,
) -> None:
    """
    配置全局 structlog 日志系统。

    Args:
        log_level: 应用 logger 的最低级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）。
        log_format: 'console'（开发美观输出）或 'json'（生产结构化输出）。
        show_timestamp: console 面板右下角是否显示时间戳。
        show_logger_name: console 标题是否显示 logger 名称。
        kv_truncate_at: console 值字段的截断阈值。
        kv_key_width: console 键列固定宽度，用于对齐。
        root_level: 根 logger 级别；默认 None 表示使用 WARNING 以降低第三方噪声。
        service: 统一绑定到日志的服务名（通过 contextvars 注入）。
        silence_noisy_libs: 是否下调常见噪声 logger 的级别（默认 True）。
    """
    if log_format == "console" and Console is None:
        raise ImportError(
            "要使用 'console' 日志格式，请先安装 rich：\n"
            "  poetry add rich --group dev\n"
            "或：pip install rich"
        )

    # 结构化处理链（官方推荐 ProcessorFormatter 桥接范式）
    pre_chain: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
    ]

    # 默认本地时间；如为 JSON 模式会在下方覆盖为 ISO+UTC
    timestamper_local = structlog.processors.TimeStamper(
        fmt="%Y-%m-%d %H:%M:%S", utc=False
    )

    processors: list[Processor] = [
        *pre_chain,
        timestamper_local,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    # JSON：ISO + UTC
    if log_format == "json":
        processors[3] = structlog.processors.TimeStamper(
            fmt="iso", utc=True
        )  # 覆盖为 ISO+UTC

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 最终渲染器
    if log_format == "console":
        final_renderer: Processor = HybridPanelRenderer(
            log_level=log_level,
            kv_truncate_at=kv_truncate_at,
            show_timestamp=show_timestamp,
            show_logger_name=show_logger_name,
            kv_key_width=kv_key_width,
        )
    else:
        final_renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=final_renderer,
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # 根记录器：默认 WARNING 抑制第三方噪声；如需覆盖可传 root_level
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel((root_level or "WARNING").upper())

    # [新增] 如果提供了 TUI 队列，则添加 TuiLogHandler
    if tui_log_queue:
        from trans_hub.presentation.tui.logging import TuiLogHandler
        tui_handler = TuiLogHandler(tui_log_queue)
        tui_handler.setFormatter(formatter)
        root_logger.addHandler(tui_handler)

    # 应用 logger：按入参设定
    app_logger = logging.getLogger("trans_hub")
    app_logger.setLevel(log_level.upper())
    app_logger.propagate = True

    # 绑定全局上下文（service 等），所有日志都会带上
    structlog.contextvars.clear_contextvars()
    if service:
        structlog.contextvars.bind_contextvars(service=service)

    # 静音常见噪声（可选）
    if silence_noisy_libs:
        for noisy in (
            "urllib3",
            "httpcore",
            "httpx",
            "asyncio",
            "sqlalchemy.engine.Engine",  # 细粒度：引擎 SQL 回显
        ):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    # 配置完成日志（使用 structlog）
    s_logger = structlog.get_logger("trans_hub.logging_config")
    s_logger.info(
        "日志系统已配置完成。",
        log_format=log_format,
        app_log_level=log_level.upper(),
        root_log_level=(root_level or "WARNING").upper(),
        service=service,
    )


# -------- 便捷入口：从 TransHubConfig 初始化 --------


def setup_logging_from_config(
    cfg: "TransHubConfig", *, service: str = "trans-hub-server"
) -> None:
    """
    根据 TransHubConfig 一键初始化日志系统。
    - cfg.logging.format: 'console' | 'json'
    - cfg.logging.level : 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
    - 其余参数使用默认值（可按需扩展）
    """
    setup_logging(
        log_level=cfg.logging.level,
        log_format=cfg.logging.format,
        service=service,
    )


# 类型仅用于注解，避免运行期循环依赖
try:  # 运行期不导入（避免配置层与观测层互相依赖），仅用于类型提示
    from trans_hub.config import TransHubConfig  # noqa: F401
except Exception:  # pragma: no cover
    pass
