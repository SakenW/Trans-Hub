# packages/server/src/trans_hub/infrastructure/db/_schema.py
"""
定义了与数据库 Alembic Schema 完全对应的 SQLAlchemy ORM 模型。
(v3.3.0 修复版)
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
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    BigInteger,
    Index,
    text,
    UUID,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# 优先使用 PostgreSQL 的 JSONB；非 PG 时回退为通用 JSON
try:
    json_type = JSONB(astext_type=Text())
except (ImportError, AttributeError):
    json_type = JSON()


class Base(DeclarativeBase):
    """ORM 基类，默认绑定 th schema。"""

    __table_args__ = {"schema": "th"}


# 与迁移中创建的 ENUM 类型一致（schema='th'）
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status", schema="th"
)


# =========================
# 核心数据表
# =========================


class ThProjects(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ThContent(Base):
    __tablename__ = "content"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th.projects.project_id", deferrable=True, initially="DEFERRED")
    )
    namespace: Mapped[str] = mapped_column(Text)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32))
    source_lang: Mapped[str] = mapped_column(Text)
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"
        ),
        {"schema": "th"},
    )


class ThTransRev(Base):
    __tablename__ = "trans_rev"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th.content.id", ondelete="CASCADE")
    )
    target_lang: Mapped[str] = mapped_column(Text)
    variant_key: Mapped[str] = mapped_column(Text, server_default="-")
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(translation_status_enum)
    origin_lang: Mapped[str | None] = mapped_column(Text, nullable=True)
    src_payload_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    translated_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        json_type, nullable=True
    )
    engine_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "content_id",
            "target_lang",
            "variant_key",
            "revision_no",
            name="uq_rev_dim",
        ),
        {"schema": "th"},
    )


class ThTransHead(Base):
    __tablename__ = "trans_head"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th.content.id", ondelete="CASCADE")
    )
    target_lang: Mapped[str] = mapped_column(Text)
    variant_key: Mapped[str] = mapped_column(Text, server_default="-")
    current_rev_id: Mapped[str] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(translation_status_enum)
    current_no: Mapped[int] = mapped_column(Integer)
    published_rev_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # [修复] 定义 ORM 关系，让 selectinload 可以工作
    content: Mapped["ThContent"] = relationship(back_populates=None)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"
        ),
        UniqueConstraint(
            "project_id", "published_rev_id", name="uq_head_published_rev"
        ),
        ForeignKeyConstraint(
            ["project_id", "current_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["project_id", "published_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        {"schema": "th"},
    )


class ThResolveCache(Base):
    __tablename__ = "resolve_cache"

    project_id: Mapped[str] = mapped_column(
        Text, ForeignKey("th.projects.project_id"), primary_key=True
    )
    content_id: Mapped[str] = mapped_column(Text, primary_key=True)
    target_lang: Mapped[str] = mapped_column(Text, primary_key=True)
    variant_key: Mapped[str] = mapped_column(Text, primary_key=True, server_default="-")
    resolved_rev_id: Mapped[str] = mapped_column(Text)
    resolved_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    origin_lang: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "resolved_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["content_id"], ["th.content.id"], ondelete="CASCADE"),
        {"schema": "th"},
    )


class ThTmUnits(Base):
    __tablename__ = "tm_units"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th.projects.project_id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(Text)
    src_lang: Mapped[str] = mapped_column(Text)
    tgt_lang: Mapped[str] = mapped_column(Text)
    src_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    src_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    tgt_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    variant_key: Mapped[str] = mapped_column(Text, server_default="-")
    approved: Mapped[bool] = mapped_column(Boolean, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "namespace",
            "src_hash",
            "tgt_lang",
            "variant_key",
            name="uq_tm_units_dim",
        ),
        {"schema": "th"},
    )


class ThTmLinks(Base):
    __tablename__ = "tm_links"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(Text)
    translation_rev_id: Mapped[str] = mapped_column(Text)
    tm_id: Mapped[str] = mapped_column(ForeignKey("th.tm_units.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"
        ),
        ForeignKeyConstraint(
            ["project_id", "translation_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            ondelete="CASCADE",
        ),
        Index("ix_tm_links_tm_id", "project_id", "tm_id"),
        {"schema": "th"},
    )


class ThLocalesFallbacks(Base):
    __tablename__ = "locales_fallbacks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("th.projects.project_id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(Text, primary_key=True)
    fallback_order: Mapped[list[str]] = mapped_column(json_type)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThEvents(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    project_id: Mapped[str] = mapped_column(Text)
    head_id: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            ondelete="CASCADE",
        ),
        {"schema": "th"},
    )


class ThComments(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    project_id: Mapped[str] = mapped_column(Text)
    head_id: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            ondelete="CASCADE",
        ),
        {"schema": "th"},
    )


class ThOutboxEvents(Base):
    """[修复] 事务性发件箱表，字段与 Alembic 迁移完全对齐。"""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, server_default="pending", index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[dict[str, Any] | None] = mapped_column(json_type, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, server_default="1")
    event_id: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "topic", "event_id", name="ux_outbox_project_topic_event"
        ),
        {"schema": "th"},
    )