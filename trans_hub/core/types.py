# trans_hub/core/types.py
"""
本模块定义了 Trans-Hub 系统的核心数据类型。
此版本已完全升级至 UIDA 架构。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, Field


class TranslationStatus(str, Enum):
    """表示翻译记录在其生命周期中的不同状态 (UIDA 模型)。"""
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"
    # 内部 worker 使用的临时状态，非权威指南要求，但对工作流有帮助
    # 可以在后续讨论中决定是否需要
    PENDING_TRANSLATION = "pending_translation" 
    TRANSLATING = "translating"
    FAILED = "failed"


class EngineSuccess(BaseModel):
    """代表从翻译引擎成功返回的单次翻译结果。"""
    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    """代表从翻译引擎返回的单次失败结果，并指明是否可重试。"""
    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]


class ContentItem(BaseModel):
    """
    在内部处理流程中，代表一个从数据库取出的、准备进行翻译处理的原子任务 (UIDA 模型)。
    它携带了执行翻译所需的所有上下文信息。
    """
    translation_id: str
    content_id: str
    project_id: str
    namespace: str
    source_payload: dict[str, Any]
    source_lang: str | None
    target_lang: str
    variant_key: str


class TranslationRequest:
    """旧的 TranslationRequest 已被 UIDA 模型取代，此类不再需要。"""
    pass


class TranslationResult(BaseModel):
    """代表一个已完成的翻译结果的 Pydantic 模型，用于 Worker 返回给 Coordinator。"""
    translation_id: str
    content_id: str
    status: TranslationStatus
    translated_payload: dict[str, Any] | None = None
    engine_name: str | None = None
    engine_version: str | None = None
    error: str | None = None