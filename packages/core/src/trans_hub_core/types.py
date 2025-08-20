# packages/core/src/trans_hub_core/types.py
"""
本模块定义了 Trans-Hub 系统的核心数据类型。
这些类型是系统各层之间数据交换的契约。
(v3.0.0 重构版)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Union

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from trans_hub.infrastructure.uow import UowFactory
    from trans_hub.config import TransHubConfig


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
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    content_id: str
    target_lang: str
    variant_key: str
    current_rev_id: str
    current_status: TranslationStatus
    current_no: int
    published_rev_id: str | None = None
    published_no: int | None = None
    published_at: datetime | None = None

    @classmethod
    def from_orm_model(cls, orm_obj: Any) -> "TranslationHead":
        """
        [防腐层] 从 SQLAlchemy ORM 实例安全地创建 DTO。
        封装了 ORM -> DTO 的转换逻辑。
        """
        return cls.model_validate(orm_obj, from_attributes=True)

class TranslationRevision(BaseModel):
    """翻译修订记录的DTO。"""
    # [修复] 补全 ORM 模式配置
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    content_id: str
    status: TranslationStatus
    revision_no: int
    translated_payload_json: dict[str, Any] | None = None
    engine_name: str | None = None
    engine_version: str | None = None
    # [新增] 补全 origin_lang 以匹配 ORM 模型，避免验证错误
    origin_lang: str | None = None

    @classmethod
    def from_orm_model(cls, orm_obj: Any) -> "TranslationRevision":
        """
        [修复] 补全 from_orm_model 类方法
        [防腐层] 从 SQLAlchemy ORM 实例安全地创建 DTO。
        """
        return cls.model_validate(orm_obj, from_attributes=True)


class Comment(BaseModel):
    """评论记录的DTO。"""
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    head_id: str
    project_id: str
    author: str
    body: str
    created_at: datetime | None = None

    @classmethod
    def from_orm_model(cls, orm_obj: Any) -> "Comment":
        """
        [防腐层] 从 SQLAlchemy ORM 实例安全地创建 DTO。
        
        采用“预处理 -> 验证”模式，以处理 ORM 模型 (id: int) 与 
        领域 DTO (id: str) 之间的类型不匹配。
        """
        if orm_obj is None:
            raise ValueError("orm_obj cannot be None")

        data = {c.name: getattr(orm_obj, c.name) for c in orm_obj.__table__.columns}
        
        if 'id' in data and data['id'] is not None:
            data['id'] = str(data['id'])
            
        return cls.model_validate(data)

class Event(BaseModel):
    """事件记录的DTO。"""
    model_config = ConfigDict(from_attributes=True)

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
    uow_factory: "UowFactory"