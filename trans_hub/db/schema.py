# trans_hub/db/schema.py
# 遵循白皮书 Final v1.2 的数据模型
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


def _json_type(dialect_name: str) -> sa.types.TypeEngine:
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


class Base(DeclarativeBase):
    @property
    def _dialect_name(self) -> str:
        # A simple way to access dialect name from the model instance
        return self.metadata.bind.dialect.name if self.metadata.bind else "default"

    @property
    def JSONType(self) -> sa.types.TypeEngine:
        return _json_type(self._dialect_name)


# 定义 ENUM 类型以供 ORM 使用
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


class ThContent(Base):
    """源内容权威表"""
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
        CheckConstraint(
            "(octet_length(keys_sha256_bytes)=32) OR (length(keys_sha256_bytes)=32)",
            name="ck_content_keys_sha256_len",
        ),
        Index("ix_content_project_namespace", "project_id", "namespace"),
        Index("ix_content_project_namespace_version", "project_id", "namespace", "content_version"),
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
    origin_lang: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    lint_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engine_name: Mapped[str | None] = mapped_column(String)
    engine_version: Mapped[str | None] = mapped_column(String)
    prompt_hash: Mapped[str | None] = mapped_column(String)
    params_hash: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("content_id", "target_lang", "variant_key", "revision", name="uq_translations_revision"),
        Index("ix_trans_content_lang", "content_id", "target_lang"),
        Index("ix_trans_lang_status", "target_lang", "status"),
        Index("ix_trans_project_lang_status", "project_id", "target_lang", "status"),
        # 部分唯一索引需要通过 Alembic hook 或方言特定语法实现
        Index(
            "uq_translations_published",
            "content_id", "target_lang", "variant_key",
            unique=True,
            postgresql_where=(status == 'published')
        ),
    )


class ThTm(Base):
    """翻译记忆库"""
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
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    hash_algo_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reuse_policy_fingerprint: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    pii_flags: Mapped[list[str] | None] = mapped_column(JSON)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id", "namespace", "reuse_sha256_bytes",
            "source_lang", "target_lang", "variant_key",
            "policy_version", "hash_algo_version",
            name="uq_tm_reuse_key",
        ),
        CheckConstraint(
            "visibility_scope in ('project','tenant','global')",
            name="ck_tm_visibility_scope",
        ),
        CheckConstraint(
            "(octet_length(reuse_sha256_bytes)=32) OR (length(reuse_sha256_bytes)=32)",
            name="ck_tm_reuse_sha256_len",
        ),
        Index("ix_tm_last_used", "last_used_at"),
    )


class ThTmLinks(Base):
    """复用追溯"""
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