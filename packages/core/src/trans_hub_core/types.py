# src/trans_hub_core/types.py
"""
本模块定义了 Trans-Hub 系统的核心数据类型。
这些类型是系统各层之间数据交换的契约。
(Pydantic V2 语法修正版)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .interfaces import PersistenceHandler
    from trans_hub_server.config import TransHubConfig


class TranslationStatus(str, Enum):
    """表示翻译记录在其生命周期中的不同状态。"""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"


class EngineSuccess(BaseModel):
    """表示翻译引擎成功返回的结果。"""
    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    """表示翻译引擎执行失败。"""
    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]


class ContentItem(BaseModel):
    """在内部处理流程中，代表一个从数据库取出的、准备进行翻译处理的原子任务。"""
    head_id: str
    current_rev_id: str
    current_no: int
    content_id: str
    project_id: str
    namespace: str
    source_payload: dict[str, Any]
    source_lang: str
    target_lang: str
    variant_key: str


class TranslationHead(BaseModel):
    """翻译头记录的数据传输对象 (DTO)。"""
    model_config = ConfigDict(from_attributes=True) # [修复] 使用 Pydantic V2 的 ConfigDict

    id: str
    project_id: str
    content_id: str
    target_lang: str
    variant_key: str
    current_rev_id: str
    current_status: TranslationStatus
    current_no: int
    published_rev_id: str | None = None

class TranslationRevision(BaseModel):
    """翻译修订记录的DTO。"""
    model_config = ConfigDict(from_attributes=True) # [修复]

    id: str
    project_id: str
    content_id: str
    status: TranslationStatus
    revision_no: int

class Comment(BaseModel):
    """评论记录的DTO。"""
    model_config = ConfigDict(from_attributes=True) # [修复]

    id: str | None = None
    head_id: str
    project_id: str
    author: str
    body: str
    created_at: datetime | None = None

class Event(BaseModel):
    """事件记录的DTO。"""
    model_config = ConfigDict(from_attributes=True) # [修复]

    id: str | None = None
    head_id: str
    project_id: str
    actor: str
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ProcessingContext:
    """一个“工具箱”对象，封装了处理策略执行时所需的所有依赖项。"""

    config: "TransHubConfig"
    handler: "PersistenceHandler"