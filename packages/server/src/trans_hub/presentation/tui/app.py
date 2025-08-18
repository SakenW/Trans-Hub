# packages/server/src/trans_hub/presentation/tui/app.py
"""
Trans-Hub TUI 主应用 (TransHubApp)。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header

from trans_hub.presentation.tui.controllers.app_controller import AppController
from trans_hub.presentation.tui.messages import (
    ActionPublishRevision,
    ActionRejectRevision,
    ActionShowDetails,
    ActionUnpublishRevision,
    StatusOperationFailed,
    StatusOperationSuccess,
)
from trans_hub.presentation.tui.screens.dashboard import DashboardScreen
from trans_hub.presentation.tui.screens.details import DetailsScreen
from trans_hub.presentation.tui.widgets.log_viewer import LogViewer

if TYPE_CHECKING:
    from trans_hub.application import Coordinator


class TransHubApp(App):
    """一个用于管理 Trans-Hub 翻译流程的 Textual 应用。"""

    CSS_PATH = "app.css"
    BINDINGS = [
        Binding("d", "push_screen('dashboard')", "仪表盘", priority=True),
        Binding("l", "toggle_log", "日志"),
        Binding("r", "action_refresh_heads", "刷新"),
        Binding("q", "quit", "退出"),
    ]

    def __init__(self, coordinator: Coordinator, dev_mode: bool = False):
        super().__init__()
        self.coordinator = coordinator
        self.dev_mode = dev_mode
        self.controller = AppController(self, coordinator)
        self.log_viewer_container = Container(LogViewer(self.controller.state), id="log_viewer_container")

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.log_viewer_container
        yield Footer()

    def on_mount(self) -> None:
        """在应用挂载时启动后台任务。"""
        self.install_screen(DashboardScreen(), name="dashboard")
        self.install_screen(DetailsScreen(head_id=""), name="details")
        self.push_screen("dashboard")
        
        self.run_worker(self.controller.stream_logs, name="log_stream", exclusive=True, group="background")
        self.action_refresh_heads()

    def action_refresh_heads(self) -> None:
        self.notify("正在刷新列表...")
        self.run_worker(self.controller.refresh_heads, name="manual_refresh", exclusive=True)

    def action_toggle_log(self) -> None:
        self.log_viewer_container.toggle_class("hidden")

    def on_action_show_details(self, message: ActionShowDetails) -> None:
        self.switch_screen(DetailsScreen(head_id=message.head_id))

    def on_action_publish_revision(self, message: ActionPublishRevision) -> None:
        rev_id = message.revision_id
        self.run_worker(lambda: self.controller.publish_revision(rev_id), name=f"publish-{rev_id[:8]}", exclusive=True)

    def on_action_unpublish_revision(self, message: ActionUnpublishRevision) -> None:
        rev_id = message.revision_id
        self.run_worker(lambda: self.controller.unpublish_revision(rev_id), name=f"unpublish-{rev_id[:8]}", exclusive=True)

    def on_action_reject_revision(self, message: ActionRejectRevision) -> None:
        rev_id = message.revision_id
        self.run_worker(lambda: self.controller.reject_revision(rev_id), name=f"reject-{rev_id[:8]}", exclusive=True)

    def on_status_operation_failed(self, message: StatusOperationFailed) -> None:
        self.notify(message.error_message, title="操作失败", severity="error", timeout=5)

    def on_status_operation_success(self, message: StatusOperationSuccess) -> None:
        self.notify(message.message, title="操作成功", severity="information", timeout=3)