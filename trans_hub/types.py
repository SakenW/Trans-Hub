"""
trans_hub/types.py

本模块定义了 Trans-Hub 引擎的核心数据传输对象 (DTOs)、枚举和数据结构。
它是应用内部数据契约的“单一事实来源”。
"""
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field

# ==============================================================================
#  枚举 (Enumerations)
# ==============================================================================

class TranslationStatus(str, Enum):
    """
    表示翻译记录在数据库中的生命周期状态。

    - PENDING: 翻译请求已被记录，等待处理。
    - TRANSLATING: 条目已被工作进程拾取，正在发送给翻译引擎。
    - TRANSLATED: 已成功从引擎接收到翻译结果。
    - FAILED: 在所有重试次数用尽后，翻译过程失败。
    - APPROVED: 翻译结果已经过人工审核并批准。
    """
    PENDING = "PENDING"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    FAILED = "FAILED"
    APPROVED = "APPROVED"

# ==============================================================================
#  引擎层 DTOs (与 TranslationEngine 的交互)
# ==============================================================================

class EngineSuccess(BaseModel):
    """代表从引擎返回的单次成功翻译结果。"""
    translated_text: str  # 翻译后的文本内容
    detected_source_lang: Optional[str] = None  # 引擎检测到的源语言，可选


class EngineError(BaseModel):
    """代表引擎针对单个文本返回的错误信息。"""
    error_message: str  # 具体的错误描述
    is_retryable: bool  # 指示该错误是否是临时性的，是否应该重试
    # 未来可以扩展，加入错误码等元数据
    # error_code: Optional[str] = None

# 用于表示引擎对单个文本翻译结果的联合类型
EngineBatchItemResult = Union[EngineSuccess, EngineError]


# ==============================================================================
#  协调器层 DTOs (公共 API 与持久化层使用)
# ==============================================================================

class TranslationResult(BaseModel):
    """
    由协调器（Coordinator）返回给最终用户的综合结果对象。
    它代表了对单个文本翻译尝试的最终状态。
    """
    original_text: str  # 原始文本
    translated_text: Optional[str] = None  # 翻译后的文本，如果失败则为 None
    target_lang: str  # 目标语言代码
    status: TranslationStatus  # 本次翻译的最终状态
    engine: Optional[str] = None  # 使用的翻译引擎名称，可选
    error: Optional[str] = None  # 如果发生错误，记录错误信息
    from_cache: bool  # 结果是否来自缓存

    # 用于关联回业务逻辑
    business_id: Optional[str] = Field(default=None, description="与此文本关联的业务ID，如果有的话。")


class SourceUpdateResult(BaseModel):
    """
    在 PersistenceHandler 中执行 update_or_create_source 操作的结果。
    """
    text_id: int  # 关联的文本在 th_texts 表中的 ID
    is_newly_created: bool  # 文本是否是新创建的


class TextItem(BaseModel):
    """
    一个结构化的、用于内部处理的待翻译文本条目。
    """
    text_id: int  # 文本在 th_texts 表中的 ID
    text_content: str  # 文本内容
    context_hash: Optional[str]  # 上下文哈希值