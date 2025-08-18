# packages/server/src/trans_hub/presentation/tui/screens/dashboard.py
"""
TUI 仪表盘屏幕，显示翻译头列表。
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from trans_hub.presentation.tui.messages import ActionShowDetails, EventHeadsUpdated

if TYPE_CHECKING:
    from textual.app import App
    from trans_hub.presentation.tui.state import TuiState
    from trans_hub_core.types import TranslationHead

class TranslationHeadTable(DataTable):
    """一个用于显示 TranslationHead 列表的表格组件。"""

    def __init__(self, state: "TuiState", **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.cursor_type = "row"

    def on_mount(self) -> None:
        """在挂载时设置表格列，并显示加载提示。"""
        self.add_columns(
            "ID", "Project", "Namespace", "Target Lang", "Variant", "Status", "Rev #"
        )
        self.loading = True # 显示加载指示器

    def watch_heads(self, new_heads: list["TranslationHead"]) -> None:
        """响应 TuiState.heads 的变化。"""
        self.loading = False # 隐藏加载指示器
        self._update_rows(new_heads)

    def _update_rows(self, heads: list["TranslationHead"]) -> None:
        """用新的数据更新表格行。"""
        self.clear()
        for head in heads:
            self.add_row(
                head.id[:8],
                head.project_id,
                # 简单截断以适应UI
                head.content_id[:15] + "...",
                head.target_lang,
                head.variant_key,
                head.current_status.value.upper(),
                head.current_no,
                key=head.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """当用户选择一行时，发出显示详情的动作。"""
        self.post_message(ActionShowDetails(head_id=str(event.row_key.value)))

class DashboardScreen(Screen):
    """应用的主仪表盘。"""

    BINDINGS = [Binding("enter", "show_details", "查看详情", show=False)]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.table = TranslationHeadTable(self.app.controller.state, id="heads_table")

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="dashboard-container"):
            yield self.table
        yield Footer()

    def on_mount(self) -> None:
        """在屏幕挂载时绑定响应式属性。"""
        self.watch(self.app.controller.state, "heads", self.on_heads_updated, init=False)
        # 初始加载时，表格会显示 loading 状态
        if self.app.controller.state.heads:
            self.on_heads_updated(self.app.controller.state.heads)

    def on_heads_updated(self, heads: list["TranslationHead"]) -> None:
        """当中控状态更新时，同步到表格。"""
        self.table.watch_heads(heads)

    def action_show_details(self) -> None:
        """处理 'enter' 键，触发详情显示。"""
        if self.table.cursor_row >= 0:
            row_key = self.table.get_row_at(self.table.cursor_row)[-1]
            self.post_message(ActionShowDetails(head_id=str(row_key.value)))