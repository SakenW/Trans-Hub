# trans_hub/db/schema.py
# [v2.4 Refactor] 根据白皮书 v2.4 全面重构数据模型，与 3f8b9e6a0c2c 迁移脚本完全对齐。
# 引入 ThProjects, ThTransRev, ThTransHead, SearchContent, ThResolveCache 等新表。
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import TypeEngine

# 定义 ENUM 类型以供 ORM 使用
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


def _json_type(dialect_name: str) -> TypeEngine:
    """根据方言选择 JSON 或 JSONB。"""
    if dialect_name == "postgresql":
        return JSONB(astext_type=Text())
    return JSON


class Base(DeclarativeBase):
    """自定义的声明式基类，提供方言相关的便利属性。"""

    @property
    def _dialect_name(self) -> str:
        return self.metadata.bind.dialect.name if self.metadata.bind else "default"

    @property
    def JSONType(self) -> TypeEngine:
        return _json_type(self._dialect_name)


class ThProjects(Base):
    """项目集中注册表"""

    __tablename__ = "th_projects"
    project_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="项目主键（短而稳）")
    display_name: Mapped[str] = mapped_column(String, nullable=False, comment="自然名（便于人读）")
    category: Mapped[str | None] = mapped_column(String, comment="元数据：mod/pack/app/web/site 等")
    platform: Mapped[str | None] = mapped_column(String, comment="元数据：minecraft/ios/android/web 等")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        CheckConstraint("char_length(project_id) BETWEEN 3 AND 32", name="ck_proj_len"),
    )


class ThContent(Base):
    """源内容权威表"""

    __tablename__ = "th_content"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("th_projects.project_id"), nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    keys_b64: Mapped[str] = mapped_column(Text, nullable=False, comment="JCS(keys_json) 的 Base64URL 文本")
    keys_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="权威 keys（I-JSON；参与 UIDA）")
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),
    )


class ThTransRev(Base):
    """翻译修订历史表 (Append-only)"""

    __tablename__ = "th_trans_rev"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("th_projects.project_id"), nullable=False)
    content_id: Mapped[str] = mapped_column(ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, server_default="-")
    status: Mapped[str] = mapped_column(translation_status_enum, nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    translated_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    origin_lang: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    lint_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_name: Mapped[str | None] = mapped_column(String)
    engine_version: Mapped[str | None] = mapped_column(String)
    prompt_hash: Mapped[str | None] = mapped_column(String)
    params_hash: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ThTransHead(Base):
    """翻译头表 (维度唯一行，指向当前/已发布修订)"""

    __tablename__ = "th_trans_head"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("th_projects.project_id"), nullable=False)
    content_id: Mapped[str] = mapped_column(ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, server_default="-")
    current_rev_id: Mapped[str] = mapped_column(ForeignKey("th_trans_rev.id"), nullable=False)
    current_status: Mapped[str] = mapped_column(translation_status_enum, nullable=False)
    current_no: Mapped[int] = mapped_column(Integer, nullable=False)
    published_rev_id: Mapped[str | None] = mapped_column(ForeignKey("th_trans_rev.id"))
    published_no: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"),
    )


class SearchContent(Base):
    """影子索引表"""

    __tablename__ = "search_content"
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th_content.id", ondelete="CASCADE"), primary_key=True
    )
    # 按需追加扁平化字段...


class ThTm(Base):
    """翻译记忆库"""

    __tablename__ = "th_tm"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    reuse_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    source_text_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    translated_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, server_default="-")
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    hash_algo_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    quality_score: Mapped[float | None] = mapped_column(Float)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "project_id", "namespace", "reuse_sha256_bytes", "source_lang",
            "target_lang", "variant_key", "policy_version", "hash_algo_version",
            name="uq_tm_reuse_key",
        ),
    )


class ThTmLinks(Base):
    """复用追溯"""

    __tablename__ = "th_tm_links"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    translation_rev_id: Mapped[str] = mapped_column(
        ForeignKey("th_trans_rev.id", ondelete="CASCADE"), nullable=False
    )
    tm_id: Mapped[str] = mapped_column(ForeignKey("th_tm.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("translation_rev_id", "tm_id", name="uq_tm_links_pair"),)


class ThLocalesFallbacks(Base):
    """语言回退策略"""

    __tablename__ = "th_locales_fallbacks"
    project_id: Mapped[str] = mapped_column(ForeignKey("th_projects.project_id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String, primary_key=True)
    fallback_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ThResolveCache(Base):
    """运行时解析缓存"""

    __tablename__ = "th_resolve_cache"
    content_id: Mapped[str] = mapped_column(String, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String, primary_key=True)
    variant_key: Mapped[str] = mapped_column(String, primary_key=True)
    resolved_rev: Mapped[str] = mapped_column(String, nullable=False)
    origin_lang: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)