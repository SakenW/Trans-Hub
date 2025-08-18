# packages/server/src/trans_hub/presentation/tui/state.py
"""
定义 TUI 的集中状态容器 (TuiState) 和相关的数据传输对象 (DTOs)。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from pydantic import BaseModel, Field
from trans_hub_core.types import Comment, TranslationHead, TranslationRevision


class LogEntry(BaseModel):
    """表示一条日志记录。"""
    timestamp: str
    level: str
    message: str
    logger_name: str
    extra: dict[str, Any] = Field(default_factory=dict)


class TranslationDetail(BaseModel):
    """封装了一个 TranslationHead 及其所有关联的 Revisions 和 Comments。"""
    head: TranslationHead
    revisions: list[TranslationRevision]
    comments: list[Comment]


class TuiState(BaseModel):
    """
    TUI 应用的单一事实来源 (SSOT)。
    
    UI 组件应订阅此状态的变化并作出响应式更新。
    """
    # 核心数据
    heads: list[TranslationHead] = Field(default_factory=list)
    # [新增] 详情缓存，实现多屏状态隔离
    details_cache: dict[str, TranslationDetail] = Field(default_factory=dict)
    
    # 日志与操作状态
    logs: deque[LogEntry] = Field(default_factory=lambda: deque(maxlen=1000))
    last_operation_status: Optional[str] = None
    last_operation_message: Optional[str] = None

    class Config:
        # 允许在 Pydantic 模型中使用 `deque`
        arbitrary_types_allowed = True