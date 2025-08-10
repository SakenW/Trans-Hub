# packages/server/src/trans_hub/infrastructure/db/_schema.py
"""
定义了与数据库 `3f8b9e6a0c2c` Schema 完全对应的 SQLAlchemy ORM 模型。
(最终完整对齐版)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

try:
    json_type = JSONB(astext_type=Text())
except (ImportError, AttributeError):
    json_type = JSON()

class Base(DeclarativeBase):
    """ORM 模型的基类。"""
    pass

translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)

# --- 核心模型 ---

class ThProjects(Base):
    __tablename__ = "th_projects"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str | None] = mapped_column(String, nullable=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(json_type, server_default="{}")
    is_archived: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ThContent(Base):
    __tablename__ = "th_content"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("th_projects.project_id"))
    namespace: Mapped[str] = mapped_column(String)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32))
    keys_b64: Mapped[str] = mapped_column(Text)
    keys_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    content_version: Mapped[int] = mapped_column(Integer, server_default="1")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),)

class ThTransRev(Base):
    __tablename__ = "th_trans_rev"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id: Mapped[str] = mapped_column(ForeignKey("th_content.id", ondelete="CASCADE"))
    target_lang: Mapped[str] = mapped_column(String)
    variant_key: Mapped[str] = mapped_column(String, server_default="-")
    status: Mapped[str] = mapped_column(translation_status_enum)
    revision_no: Mapped[int] = mapped_column(Integer)
    translated_payload_json: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    origin_lang: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_name: Mapped[str | None] = mapped_column(String, nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["th_projects.project_id"]),
        UniqueConstraint("project_id", "content_id", "target_lang", "variant_key", "revision_no", name="uq_rev_dim_no"),
    )

class ThTransHead(Base):
    __tablename__ = "th_trans_head"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id: Mapped[str] = mapped_column(ForeignKey("th_content.id", ondelete="CASCADE"))
    target_lang: Mapped[str] = mapped_column(String)
    variant_key: Mapped[str] = mapped_column(String, server_default="-")
    current_rev_id: Mapped[str] = mapped_column(String)
    current_status: Mapped[str] = mapped_column(translation_status_enum)
    current_no: Mapped[int] = mapped_column(Integer)
    published_rev_id: Mapped[str | None] = mapped_column(String, nullable=True)
    published_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"),
        UniqueConstraint("project_id", "published_rev_id", name="uq_head_published_rev"),
        ForeignKeyConstraint(["project_id"], ["th_projects.project_id"]),
        ForeignKeyConstraint(["project_id", "current_rev_id"], ["th_trans_rev.project_id", "th_trans_rev.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["project_id", "published_rev_id"], ["th_trans_rev.project_id", "th_trans_rev.id"], ondelete="RESTRICT"),
    )

# --- [修复] 补全以下所有模型 ---

class ThResolveCache(Base):
    __tablename__ = "th_resolve_cache"
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    content_id: Mapped[str] = mapped_column(String, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String, primary_key=True)
    variant_key: Mapped[str] = mapped_column(String, primary_key=True)
    resolved_rev_id: Mapped[str] = mapped_column(String, nullable=False) # Renamed from resolved_rev
    resolved_payload: Mapped[dict[str, Any]] = mapped_column(json_type) # Added this field
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["project_id", "resolved_rev_id"], ["th_trans_rev.project_id", "th_trans_rev.id"], ondelete="CASCADE"),)

class ThTm(Base):
    __tablename__ = 'th_tm'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String)
    namespace: Mapped[str] = mapped_column(String)
    reuse_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32))
    source_text_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    translated_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    variant_key: Mapped[str] = mapped_column(String, server_default='-')
    source_lang: Mapped[str] = mapped_column(String)
    target_lang: Mapped[str] = mapped_column(String)
    visibility_scope: Mapped[str] = mapped_column(String, server_default='project')
    policy_version: Mapped[int] = mapped_column(Integer, server_default='1')
    hash_algo_version: Mapped[int] = mapped_column(Integer, server_default='1')
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("project_id", "namespace", "reuse_sha256_bytes", "source_lang", "target_lang", "variant_key", "policy_version", "hash_algo_version", name="uq_tm_reuse_key"),)

class ThTmLinks(Base):
    __tablename__ = 'th_tm_links'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String)
    translation_rev_id: Mapped[str] = mapped_column(String)
    tm_id: Mapped[str] = mapped_column(ForeignKey('th_tm.id', ondelete='CASCADE'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint('project_id', 'translation_rev_id', 'tm_id', name='uq_tm_links_triplet'),
        ForeignKeyConstraint(['project_id', 'translation_rev_id'], ['th_trans_rev.project_id', 'th_trans_rev.id'], ondelete="CASCADE"),
    )

class ThLocalesFallbacks(Base):
    __tablename__ = 'th_locales_fallbacks'
    project_id: Mapped[str] = mapped_column(ForeignKey('th_projects.project_id'), primary_key=True)
    locale: Mapped[str] = mapped_column(String, primary_key=True)
    fallback_order: Mapped[list[str]] = mapped_column(json_type)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ThTransEvent(Base):
    __tablename__ = "th_trans_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String)
    head_id: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["project_id", "head_id"], ["th_trans_head.project_id", "th_trans_head.id"], ondelete="CASCADE"),)

class ThTransComment(Base):
    __tablename__ = "th_trans_comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String)
    head_id: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["project_id", "head_id"], ["th_trans_head.project_id", "th_trans_head.id"], ondelete="CASCADE"),)