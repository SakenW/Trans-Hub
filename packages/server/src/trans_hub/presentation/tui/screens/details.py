# packages/server/src/trans_hub/presentation/tui/screens/details.py
"""
TUI 详情屏幕，展示单个翻译任务的完整信息和操作。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from trans_hub.presentation.tui.messages import (
    ActionPublishRevision,
    ActionRejectRevision,
    ActionUnpublishRevision,
    EventDetailsUpdated,
)

if TYPE_CHECKING:
    from trans_hub.presentation.tui.state import TranslationDetail

class DetailsView(Static):
    """显示单个翻译任务详情的复合组件。"""

    def __init__(self, head_id: str, **kwargs):
        super().__init__(**kwargs)
        self.head_id = head_id
        self._details: Optional[TranslationDetail] = None

    def compose(self) -> ComposeResult:
        yield Static("加载中...", id="details-header")
        yield DataTable(id="revisions-table", cursor_type="row")
        yield Static("评论区:", classes="section-title")
        yield Vertical(id="comments-container", classes="details-box")
        with Horizontal(id="actions-container"):
            yield Button("发布 (P)", id="btn-publish", variant="success", disabled=True)
            yield Button("撤回 (U)", id="btn-unpublish", variant="warning", disabled=True)
            yield Button("拒绝 (X)", id="btn-reject", variant="error", disabled=True)

    def on_mount(self) -> None:
        """挂载时获取初始数据。"""
        self.run_worker(self.app.controller.fetch_details(self.head_id), exclusive=True)

    def on_event_details_updated(self, message: EventDetailsUpdated) -> None:
        """当详情数据更新时，刷新视图。"""
        if message.head_id == self.head_id:
            self._details = self.app.controller.state.details_cache.get(self.head_id)
            self.render_details()

    def render_details(self) -> None:
        """使用 state 中的数据填充所有 UI 元素。"""
        if not self._details:
            return

        # 更新头部信息
        head = self._details.head
        header_text = f"[b]ID:[/] {head.id[:8]}  [b]状态:[/] {head.current_status.value.upper()}"
        self.query_one("#details-header", Static).update(header_text)

        # 更新修订表格
        rev_table = self.query_one("#revisions-table", DataTable)
        rev_table.clear()
        if not rev_table.columns:
            rev_table.add_columns("Rev#", "Status", "Text", "Engine", "ID")
        for rev in self._details.revisions:
            payload = rev.translated_payload_json or {}
            rev_table.add_row(
                rev.revision_no,
                rev.status.value.upper(),
                payload.get("text", "-"),
                f"{rev.engine_name or '-'}",
                rev.id,
                key=rev.id,
            )

        # 更新评论区
        comments_container = self.query_one("#comments-container", Vertical)
        comments_container.remove_children()
        for comment in self._details.comments:
            comments_container.mount(Static(f"[b]{comment.author}:[/] {comment.body}"))
        
        # 更新按钮状态
        self.update_button_states()

    def update_button_states(self) -> None:
        """根据当前选中的修订状态更新按钮的可用性。"""
        rev_table = self.query_one("#revisions-table", DataTable)
        if not self._details or rev_table.cursor_row < 0:
            return
        
        selected_rev_id = rev_table.get_row_key(rev_table.cursor_row)
        selected_rev = next((r for r in self._details.revisions if r.id == selected_rev_id), None)

        self.query_one("#btn-publish", Button).disabled = not (selected_rev and selected_rev.status == "reviewed")
        self.query_one("#btn-unpublish", Button).disabled = not (selected_rev and selected_rev.status == "published")
        self.query_one("#btn-reject", Button).disabled = not (selected_rev and selected_rev.status not in ["rejected", "draft"])

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """行选择变化时更新按钮状态。"""
        self.update_button_states()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理按钮点击事件。"""
        rev_table = self.query_one("#revisions-table", DataTable)
        if rev_table.cursor_row < 0:
            return
        
        selected_rev_id = str(rev_table.get_row_key(rev_table.cursor_row))
        
        if event.button.id == "btn-publish":
            self.post_message(ActionPublishRevision(selected_rev_id))
        elif event.button.id == "btn-unpublish":
            self.post_message(ActionUnpublishRevision(selected_rev_id))
        elif event.button.id == "btn-reject":
            self.post_message(ActionRejectRevision(selected_rev_id))


class DetailsScreen(Screen):
    """用于显示翻译任务详情的屏幕。"""
    BINDINGS = [
        Binding("p", "publish", "发布", show=False),
        Binding("u", "unpublish", "撤回", show=False),
        Binding("x", "reject", "拒绝", show=False),
    ]
    
    def __init__(self, head_id: str, **kwargs):
        super().__init__(**kwargs)
        self.head_id = head_id
        self._view = DetailsView(head_id=self.head_id)

    def compose(self) -> ComposeResult:
        yield Header()
        yield self._view
        yield Footer()

    def action_publish(self): self.query_one("#btn-publish").press()
    def action_unpublish(self): self.query_one("#btn-unpublish").press()
    def action_reject(self): self.query_one("#btn-reject").press()