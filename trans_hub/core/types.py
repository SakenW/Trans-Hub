# trans_hub/core/types.py
# [v2.4.1 Final] 在 ContentItem 中添加缺失的 head_id 和 revision_no 字段。
"""
本模块定义了 Trans-Hub 系统的核心数据类型。
此版本已完全升级至白皮书 Final v1.2。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    from trans_hub.core.interfaces import PersistenceHandler


class TranslationStatus(str, Enum):
    """表示翻译记录在其生命周期中的不同状态 (白皮书 v1.2)。"""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    REJECTED = "rejected"


class EngineSuccess(BaseModel):
    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]


class ContentItem(BaseModel):
    """在内部处理流程中，代表一个从数据库取出的、准备进行翻译处理的原子任务。"""

    translation_id: str  # 这是 rev_id
    # [核心修正] 添加 head_id 和 revision_no
    head_id: str
    revision_no: int

    content_id: str
    project_id: str
    namespace: str
    source_payload: dict[str, Any]
    source_lang: str | None
    target_lang: str
    variant_key: str


class TranslationResult(BaseModel):
    """代表一个已完成的翻译结果的 Pydantic 模型，用于 Worker 返回给 Coordinator。"""

    translation_id: str
    content_id: str
    status: TranslationStatus
    translated_payload: dict[str, Any] | None = None
    engine_name: str | None = None
    engine_version: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ProcessingContext:
    """一个“工具箱”对象，封装了处理策略执行时所需的所有依赖项。"""

    config: TransHubConfig
    handler: PersistenceHandler
