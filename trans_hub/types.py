# trans_hub/types.py (最终优化版)
"""
本模块定义了 Trans-Hub 引擎的核心数据传输对象 (DTOs)、枚举和数据结构。
它是应用内部数据契约的“单一事实来源”。.
"""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator

# ==============================================================================
#  枚举 (Enumerations)
# ==============================================================================


class TranslationStatus(str, Enum):
    """表示翻译记录在数据库中的生命周期状态。."""

    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"


# ==============================================================================
#  引擎层 DTOs
# ==============================================================================


class EngineSuccess(BaseModel):
    """代表从翻译引擎返回的单次 *成功* 的翻译结果。."""

    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    """代表从翻译引擎返回的单次 *失败* 的翻译结果。."""

    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]

# ==============================================================================
#  协调器与持久化层 DTOs
# ==============================================================================


class TranslationRequest(BaseModel):
    """表示一个用于缓存查找或内部传递的翻译请求。."""

    source_text: str
    source_lang: Optional[str]
    target_lang: str
    context_hash: str


class TranslationResult(BaseModel):
    """由 Coordinator 返回给最终用户的综合结果对象，包含了完整的上下文信息。."""

    # 核心内容
    original_content: str
    translated_content: Optional[str] = None
    target_lang: str

    # 状态与元数据
    status: TranslationStatus
    engine: Optional[str] = None
    from_cache: bool
    error: Optional[str] = None

    # 来源与上下文标识
    business_id: Optional[str] = Field(
        default=None, description="与此内容关联的业务ID。"
    )
    context_hash: str = Field(description="用于区分不同上下文翻译的哈希值。")

    # --- 核心修正：添加模型验证器以确保逻辑一致性 ---
    @model_validator(mode="after")
    def check_consistency(self) -> "TranslationResult":
        """确保模型状态的逻辑一致性。."""
        if (
            self.status == TranslationStatus.TRANSLATED
            and self.translated_content is None
        ):
            raise ValueError("TRANSLATED 状态的结果必须包含 translated_content。")
        if self.status == TranslationStatus.FAILED and self.error is None:
            raise ValueError("FAILED 状态的结果必须包含 error 信息。")
        return self


class SourceUpdateResult(BaseModel):
    """`PersistenceHandler.update_or_create_source` 方法的返回结果。."""

    content_id: int
    is_newly_created: bool


class ContentItem(BaseModel):
    """内部处理时，代表一个从数据库取出的待翻译任务。."""

    content_id: int
    value: str
    context_hash: str
    context: Optional[dict[str, Any]] = None


# ==============================================================================
#  常量
# ==============================================================================

# 定义一个特殊的字符串，用于表示“全局”或“无上下文”的翻译。
GLOBAL_CONTEXT_SENTINEL = "__GLOBAL__"
