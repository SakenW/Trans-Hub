# packages/server/src/trans_hub/presentation/tui/controllers/app_controller.py
"""
TUI 应用控制器，负责处理用户操作、调用业务逻辑并更新UI状态。
"""

from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Any

from trans_hub.application import Coordinator
from trans_hub.presentation.tui.messages import (
    EventDetailsUpdated,
    EventHeadsUpdated,
    StatusOperationFailed,
    StatusOperationSuccess,
)
from trans_hub.presentation.tui.state import TuiState, TranslationDetail

if TYPE_CHECKING:
    from trans_hub.presentation.tui.app import TransHubApp


class AppController:
    """
    TUI 的主控制器，是表现层与应用层之间的桥梁。
    """
    def __init__(self, app: "TransHubApp", coordinator: Coordinator) -> None:
        self.app = app
        self.coordinator = coordinator
        self.state = TuiState()
        self.log_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def refresh_heads(self) -> None:
        """[关键修复] 从 Coordinator 刷新翻译头列表。"""
        try:
            # 真实调用：从数据库获取所有翻译头
            # 注意：在真实应用中，这里需要分页
            all_heads = await self.coordinator.handler.get_all_translation_heads()
            self.state.heads = sorted(all_heads, key=lambda h: h.updated_at, reverse=True)
            self.app.post_message(EventHeadsUpdated())
            self.app.post_message(StatusOperationSuccess("刷新列表成功"))
        except Exception as e:
            self.app.post_message(StatusOperationFailed(f"刷新列表失败: {e}"))


    async def fetch_details(self, head_id: str) -> None:
        """[关键修复] 从 Coordinator 获取指定 Head ID 的详细信息。"""
        try:
            head = await self.coordinator.handler.get_head_by_id(head_id)
            if head:
                revisions = await self.coordinator.handler.get_revisions_by_head(head_id)
                comments = await self.coordinator.get_comments(head_id)
                
                details = TranslationDetail(head=head, revisions=revisions, comments=comments)
                self.state.details_cache[head_id] = details
                self.app.post_message(EventDetailsUpdated(head_id))
            else:
                raise ValueError(f"找不到 Head ID 为 {head_id} 的记录")
        except Exception as e:
            self.app.post_message(StatusOperationFailed(f"获取详情失败: {e}"))


    async def _handle_operation(self, operation: Any, *args: Any, success_msg: str) -> None:
        """通用操作处理器，封装了错误处理和消息广播。"""
        try:
            success = await operation(*args)
            if success:
                self.app.post_message(StatusOperationSuccess(success_msg))
                # 触发数据刷新
                await self.refresh_heads() # 刷新列表
                
                # 如果是针对某个修订的操作，尝试刷新其详情页
                if args and isinstance(args[0], str):
                    head = await self.coordinator.handler.get_head_by_revision(args[0])
                    if head and head.id in self.state.details_cache:
                        await self.fetch_details(head.id)
            else:
                raise RuntimeError("操作返回了失败状态 (success=False)")
        except Exception as e:
            error_message = f"操作失败: {e}"
            self.state.last_operation_status = "failed"
            self.state.last_operation_message = error_message
            self.app.post_message(StatusOperationFailed(error_message))

    # publish, unpublish, reject 方法保持不变，因为它们已经使用了正确的 _handle_operation 包装器

    async def publish_revision(self, revision_id: str) -> None:
        """发布修订。"""
        await self._handle_operation(
            self.coordinator.publish_translation, revision_id, "cli_tui_user",
            success_msg=f"修订 {revision_id[:8]} 已发布"
        )

    async def unpublish_revision(self, revision_id: str) -> None:
        """撤回发布。"""
        await self._handle_operation(
            self.coordinator.unpublish_translation, revision_id, "cli_tui_user",
            success_msg=f"修订 {revision_id[:8]} 已撤回发布"
        )

    async def reject_revision(self, revision_id: str) -> None:
        """拒绝修订。"""
        await self._handle_operation(
            self.coordinator.reject_translation, revision_id, "cli_tui_user",
            success_msg=f"修订 {revision_id[:8]} 已拒绝"
        )
    
    # stream_logs 方法保持不变
    async def stream_logs(self) -> None:
        """从队列中批量消费日志并更新状态。"""
        from trans_hub.presentation.tui.state import LogEntry
        
        while True:
            await asyncio.sleep(0.1)
            
            batch_raw: list[dict[str, Any]] = []
            while not self.log_queue.empty():
                batch_raw.append(self.log_queue.get_nowait())
            
            if batch_raw:
                batch_entries = [
                    LogEntry(
                        timestamp=log.get("timestamp", ""),
                        level=log.get("level", "info").upper(),
                        message=log.get("event", ""),
                        logger_name=log.get("logger", "unknown"),
                        extra={k: v for k, v in log.items() if k not in ["timestamp", "level", "event", "logger"]},
                    ) for log in batch_raw
                ]
                self.state.logs.extend(batch_entries)