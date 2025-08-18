# packages/server/src/trans_hub/presentation/tui/logging.py
"""
为 Textual TUI 提供自定义的日志处理器。
"""
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

class TuiLogHandler(logging.Handler):
    """一个将日志记录发送到 asyncio.Queue 的处理器。"""
    def __init__(self, queue: "asyncio.Queue[dict[str, Any]]"):
        super().__init__()
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        """
        在 structlog.stdlib.ProcessorFormatter 处理后，
        这个方法接收到的 record.msg 已经是一个字典。
        """
        if not isinstance(record.msg, dict):
            # 仅处理由 structlog 格式化后的记录
            return
        
        try:
            self.queue.put_nowait(record.msg)
        except Exception:
            # 在队列满或其它情况下静默失败，避免日志系统本身引起崩溃
            pass