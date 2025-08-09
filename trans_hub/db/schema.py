# trans_hub/db/schema.py
# UIDA 架构下的全新数据模型 (v1.0)
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# 定义 ENUM 类型以供 ORM 使用
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


class ThContent(Base):
    """源内容权威表 (UIDA 唯一)"""
    __tablename__ = "th_content"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    keys_b64: Mapped[str] = mapped_column(Text, nullable=False)
    keys_json_debug: Mapped[str | None] = mapped_column(Text)
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_type: Mapped[str | None] = mapped_column(String)
    snapshots_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),
        Index("ix_content_project_namespace", "project_id", "namespace"),
        Index("ix_content_project_namespace_version", "project_id", "namespace", "content_version"),
    )


class ThTm(Base):
    """翻译记忆库 (复用结果仓)"""
    __tablename__ = "th_tm"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    reuse_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    source_text_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    translated_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, default="-")
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(String, nullable=False, default="project")
    pii_flags: Mapped[list[str] | None] = mapped_column(JSON)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hash_algo_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reuse_policy_fingerprint: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "namespace",
            "reuse_sha256_bytes",
            "source_lang",
            "target_lang",
            "variant_key",
            "policy_version",
            "hash_algo_version",
            name="uq_tm_reuse_key",
        ),
        Index("ix_tm_last_used", "last_used_at"),
    )


class ThTranslations(Base):
    """按语言/变体的权威译文"""
    __tablename__ = "th_translations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    content_id: Mapped[str] = mapped_column(ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False)
    source_lang: Mapped[str | None] = mapped_column(String)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, default="-")
    status: Mapped[str] = mapped_column(translation_status_enum, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    translated_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tm_id: Mapped[str | None] = mapped_column(ForeignKey("th_tm.id", ondelete="SET NULL"))
    origin_lang: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    lint_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_name: Mapped[str | None] = mapped_column(String)
    engine_version: Mapped[str | None] = mapped_column(String)
    prompt_hash: Mapped[str | None] = mapped_column(String)
    params_hash: Mapped[str | None] = mapped_column(String)
    last_reviewed_by: Mapped[str | None] = mapped_column(String)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("content_id", "target_lang", "variant_key", "revision", name="uq_translations_revision"),
        Index("ix_trans_content_lang", "content_id", "target_lang"),
        Index("ix_trans_lang_status", "target_lang", "status"),
        Index("ix_trans_project_lang_status", "project_id", "target_lang", "status"),
        Index("ix_trans_tm", "tm_id"),
        # 部分唯一索引需要通过 Alembic hook 或方言特定语法实现，此处仅为 ORM 声明
        Index(
            "uq_translations_published",
            "content_id", "target_lang", "variant_key",
            unique=True,
            postgresql_where=status == 'published'
        ),
    )


class ThTmLinks(Base):
    """复用追溯 (多对多：译文 ↔ TM)"""
    __tablename__ = "th_tm_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    translation_id: Mapped[str] = mapped_column(ForeignKey("th_translations.id", ondelete="CASCADE"), nullable=False)
    tm_id: Mapped[str] = mapped_column(ForeignKey("th_tm.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("translation_id", "tm_id", name="uq_tm_links_pair"),)


class ThLocalesFallbacks(Base):
    """语言回退策略"""
    __tablename__ = "th_locales_fallbacks"

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    locale: Mapped[str] = mapped_column(String, primary_key=True)
    fallback_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ThTranslationReviews(Base):
    """审校记录"""
    __tablename__ = "th_translation_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    translation_id: Mapped[str] = mapped_column(ForeignKey("th_translations.id", ondelete="CASCADE"), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False) # approve|reject|comment
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("ix_reviews_project_translation", "project_id", "translation_id"),)


class ThTranslationEvents(Base):
    """事件流水"""
    __tablename__ = "th_translation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_table: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str | None] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        Index("ix_events_project_type", "project_id", "event_type"),
        Index("ix_events_entity", "entity_table", "entity_id"),
    )


class ThOutbox(Base):
    """可靠外发 (Outbox 模式)"""
    __tablename__ = "th_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_outbox_status", "status"),
        Index("ix_outbox_project_status", "project_id", "status", "created_at"),
    )