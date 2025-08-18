# packages/server/src/trans_hub/presentation/tui/messages.py
"""
定义 TUI 内部通信的所有消息类型，遵循 Textual 的消息传递模式。
"""

from __future__ import annotations

from textual.message import Message


# --- Action Messages (用户意图: Widget -> Controller) ---

class ActionRefreshHeads(Message):
    """请求刷新翻译头列表。"""

class ActionShowDetails(Message):
    """请求显示指定 Head ID 的详情视图。"""
    def __init__(self, head_id: str) -> None:
        self.head_id = head_id
        super().__init__()

class ActionPublishRevision(Message):
    """请求发布一个修订。"""
    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        super().__init__()

class ActionUnpublishRevision(Message):
    """请求撤回一个已发布的修订。"""
    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        super().__init__()

class ActionRejectRevision(Message):
    """请求拒绝一个修订。"""
    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id
        super().__init__()


# --- Event Messages (状态变更通知: Controller -> UI) ---

class EventHeadsUpdated(Message):
    """通知UI翻译头列表已更新。"""

class EventDetailsUpdated(Message):
    """通知UI指定 Head ID 的详情已更新。"""
    def __init__(self, head_id: str) -> None:
        self.head_id = head_id
        super().__init__()


# --- Status Messages (操作结果通知) ---

class StatusOperationSuccess(Message):
    """通知UI一个操作已成功完成。"""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__()

class StatusOperationFailed(Message):
    """通知UI一个操作失败。"""
    def __init__(self, error_message: str) -> None:
        self.error_message = error_message
        super().__init__()