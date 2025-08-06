# trans_hub/core/types.py
"""
本模块定义了 Trans-Hub 系统的核心数据类型。
v3.0.0 更新：全面转向结构化载荷（payload），并与新的数据库 Schema 对齐。
"""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator


class TranslationStatus(str, Enum):
    """表示翻译记录在其生命周期中的不同状态。"""

    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"


class EngineSuccess(BaseModel):
    """代表从翻译引擎成功返回的单次翻译结果。"""

    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    """代表从翻译引擎返回的单次失败结果，并指明是否可重试。"""

    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]


class TranslationRequest(BaseModel):
    """表示一个内部传递或用于缓存查找的翻译请求单元。"""

    source_payload: dict[str, Any]
    source_lang: Optional[str]
    target_lang: str
    context_hash: str


class TranslationResult(BaseModel):
    """由 Coordinator 返回给最终用户的综合结果对象。"""

    translation_id: str
    business_id: Optional[str] = Field(default=None)
    original_payload: dict[str, Any]
    translated_payload: Optional[dict[str, Any]] = None
    target_lang: str
    status: TranslationStatus
    engine: Optional[str] = None
    from_cache: bool
    error: Optional[str] = None
    context_hash: str

    @model_validator(mode="after")
    def check_consistency(self) -> "TranslationResult":
        """
        验证模型状态的一致性。
        """
        if (
            self.status == TranslationStatus.TRANSLATED
            and self.translated_payload is None
        ):
            raise ValueError("TRANSLATED 状态的结果必须包含 translated_payload。")
        if self.status == TranslationStatus.FAILED and self.error is None:
            raise ValueError("FAILED 状态的结果必须包含 error 信息。")
        return self


class ContentItem(BaseModel):
    """在内部处理流程中，代表一个从数据库取出的、准备进行翻译处理的原子任务。"""

    translation_id: str
    business_id: str
    content_id: str
    context_id: Optional[str]
    source_payload: dict[str, Any]
    context: Optional[dict[str, Any]]
    # v3.x 修复：增加 source_lang 字段，用于支持按请求指定源语言
    source_lang: Optional[str]


GLOBAL_CONTEXT_SENTINEL = "__GLOBAL__"
"""一个特殊的字符串常量，用作表示“全局”或“无上下文”翻译的哈希值。"""
