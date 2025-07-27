# trans_hub/types.py
"""
本模块定义了 Trans-Hub 系统的核心数据类型。

它作为应用内部数据契约的“单一事实来源”(Single Source of Truth)，包含了
所有的数据传输对象 (DTOs)、枚举和常量，确保了各组件间数据交换的一致性和类型安全。
"""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator

# ==============================================================================
#  枚举 (Enumerations)
# ==============================================================================


class TranslationStatus(str, Enum):
    """表示翻译记录在其生命周期中的不同状态。"""

    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"


# ==============================================================================
#  引擎层 DTOs (Data Transfer Objects)
# ==============================================================================


class EngineSuccess(BaseModel):
    """代表从翻译引擎成功返回的单次翻译结果。"""

    translated_text: str
    from_cache: bool = False


class EngineError(BaseModel):
    """代表从翻译引擎返回的单次失败结果，并指明是否可重试。"""

    error_message: str
    is_retryable: bool


EngineBatchItemResult = Union[EngineSuccess, EngineError]

# ==============================================================================
#  协调器与持久化层 DTOs
# ==============================================================================


class TranslationRequest(BaseModel):
    """表示一个内部传递或用于缓存查找的翻译请求单元。"""

    source_text: str
    source_lang: Optional[str]
    target_lang: str
    context_hash: str


class TranslationResult(BaseModel):
    """由 Coordinator 返回给最终用户的综合结果对象，包含完整的元数据和上下文。"""

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
        default=None, description="与此内容关联的外部业务ID。"
    )
    context_hash: str = Field(description="用于区分不同上下文翻译的确定性哈希值。")

    @model_validator(mode="after")
    def check_consistency(self) -> "TranslationResult":
        """确保模型状态的逻辑一致性。"""
        if (
            self.status == TranslationStatus.TRANSLATED
            and self.translated_content is None
        ):
            raise ValueError("TRANSLATED 状态的结果必须包含 translated_content。")
        if self.status == TranslationStatus.FAILED and self.error is None:
            raise ValueError("FAILED 状态的结果必须包含 error 信息。")
        return self


class SourceUpdateResult(BaseModel):
    """代表 `PersistenceHandler.update_or_create_source` 方法的返回结果。"""

    content_id: int
    is_newly_created: bool


class ContentItem(BaseModel):
    """在内部处理流程中，代表一个从数据库取出的、包含完整上下文的待翻译任务。"""

    content_id: int
    value: str
    context_hash: str
    context: Optional[dict[str, Any]] = None


# ==============================================================================
#  常量
# ==============================================================================

GLOBAL_CONTEXT_SENTINEL = "__GLOBAL__"
"""一个特殊的字符串常量，用作表示“全局”或“无上下文”翻译的哈希值。"""
