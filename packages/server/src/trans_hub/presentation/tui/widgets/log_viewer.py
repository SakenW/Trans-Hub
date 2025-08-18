# packages/server/src/trans_hub/presentation/tui/widgets/log_viewer.py
"""
一个可复用的 Textual 日志查看器组件。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from textual.widgets import Log

if TYPE_CHECKING:
    from trans_hub.presentation.tui.state import LogEntry, TuiState

class LogViewer(Log):
    """一个响应式地显示 TuiState.logs 的日志组件。"""

    def __init__(self, state: "TuiState", **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self._last_log_index = -1

    def on_mount(self) -> None:
        """挂载时绑定响应式属性。"""
        self.watch(self.state, "logs", self.on_logs_updated, init=False)
        self._update_logs() # 写入初始日志

    def on_logs_updated(self, logs: list) -> None:
        """当日志状态变化时，增量写入新日志。"""
        self._update_logs()

    def _update_logs(self) -> None:
        """将 state.logs 中未显示的新日志写入组件。"""
        logs = self.state.logs
        if not logs:
            return
        
        start_index = self._last_log_index + 1
        new_logs = [logs[i] for i in range(start_index, len(logs))]

        if new_logs:
            log_lines = [
                f"{log.timestamp} [{log.level:^8}] {log.message} ({log.logger_name})"
                for log in new_logs
            ]
            self.write_lines(log_lines)
            self._last_log_index = len(logs) - 1