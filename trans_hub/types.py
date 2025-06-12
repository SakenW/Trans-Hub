"""
trans_hub/types.py (v0.1)

本模块定义了 Trans-Hub 引擎的核心数据传输对象 (DTOs)、枚举和数据结构。
它是应用内部数据契约的“单一事实来源”，已根据最终版文档进行更新。
所有与外部或模块间交互的数据结构都应在此定义。
"""
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


# ==============================================================================
#  枚举 (Enumerations)
#  - 定义了整个系统中使用的固定状态集合，确保类型安全。
# ==============================================================================

class TranslationStatus(str, Enum):
    """
    表示翻译记录在数据库中的生命周期状态。
    使用 Enum 可以防止因手误输入字符串（如 'PENDINGG'）而导致的错误。
    """
    PENDING = "PENDING"  # 待处理：已创建翻译任务，等待处理。
    TRANSLATING = "TRANSLATING"  # 处理中：已被工作进程拾取，正在调用API。
    TRANSLATED = "TRANSLATED"  # 已翻译：成功获取翻译结果。
    FAILED = "FAILED"  # 失败：API调用失败且重试次数耗尽。
    APPROVED = "APPROVED"  # 已核准：人工审核并确认的最终版本。


# ==============================================================================
#  引擎层 DTOs
#  - 定义了 `Coordinator` 与 `BaseTranslationEngine` 之间交互的数据结构。
# ==============================================================================

class EngineSuccess(BaseModel):
    """代表从翻译引擎返回的单次 *成功* 的翻译结果。"""
    translated_text: str  # 翻译后的文本内容。
    detected_source_lang: Optional[str] = None  # 引擎检测到的源语言（如果引擎支持）。


class EngineError(BaseModel):
    """代表从翻译引擎返回的单次 *失败* 的翻译结果。"""
    error_message: str  # 具体的错误描述，用于日志记录。
    is_retryable: bool  # 关键标志！指示该错误是否是临时的（如网络超时），是否应该重试。


# `Union` 类型，表示引擎对一个文本的翻译结果，要么成功，要么失败。
EngineBatchItemResult = Union[EngineSuccess, EngineError]


# ==============================================================================
#  协调器与持久化层 DTOs
#  - 定义了 `Coordinator` 公共API返回以及与 `PersistenceHandler` 交互的数据结构。
# ==============================================================================

class TranslationResult(BaseModel):
    """
    由 `Coordinator` 返回给最终用户的综合结果对象，包含了完整的上下文信息。
    这是我们对外暴露的最主要的数据结构之一。
    """
    # 核心内容
    original_content: str  # [变更] 原始文本内容。
    translated_content: Optional[str] = None  # [变更] 翻译后的文本内容，失败时为 None。
    target_lang: str  # 目标语言代码，如 'en', 'zh-CN'。
    
    # 状态与元数据
    status: TranslationStatus  # 本次翻译的最终状态。
    engine: Optional[str] = None  # 使用的翻译引擎名称。
    from_cache: bool  # 结果是否来自缓存。
    error: Optional[str] = None  # 如果发生错误，记录错误信息。

    # 来源与上下文标识
    business_id: Optional[str] = Field(default=None, description="与此内容关联的业务ID。")
    context_hash: Optional[str] = Field(default=None, description="用于区分不同上下文翻译的哈希值。")


class SourceUpdateResult(BaseModel):
    """
    `PersistenceHandler.update_or_create_source` 方法的返回结果。
    封装了操作后需要返回给调用方的信息。
    """
    content_id: int  # [变更] 关联的内容在 `th_content` 表中的 ID。
    is_newly_created: bool  # 指示这个内容是否是第一次被添加到数据库中。


class ContentItem(BaseModel):
    """
    [变更] 内部处理时，代表一个待翻译任务的结构化对象。
    从 `TextItem` 更名而来，以匹配新文档的术语。
    """
    content_id: int  # [变更] 内容在 `th_content` 表中的 ID。
    value: str  # [变更] 内容的字符串值。
    context_hash: Optional[str]  # 与此翻译任务绑定的上下文哈希。