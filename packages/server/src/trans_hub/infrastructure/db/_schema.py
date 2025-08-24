# packages/server/src/trans_hub/infrastructure/db/_schema.py
"""
定义了与数据库 Alembic Schema 完全对应的 SQLAlchemy ORM 模型。
(v3.3.4 终极修复版 - 修复 relationship 字段顺序)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    UUID,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

# 优先使用 PostgreSQL 的 JSONB；非 PG 时回退为通用 JSON
try:
    json_type = JSONB(astext_type=Text())
except (ImportError, AttributeError):
    json_type = JSON()


# 与迁移中创建的 ENUM 类型一致
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


# =========================
# 核心数据表
# =========================


class ThProjects(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="TRUE", default=True, init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )

    __table_args__ = (
        {"schema": "th"},
    )

    __table_args__ = (
        {"schema": "th"},
    )


class ThContent(Base):
    __tablename__ = "content"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("th.projects.project_id", deferrable=True, initially="DEFERRED")
    )
    namespace: Mapped[str] = mapped_column(Text)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32))
    source_lang: Mapped[str] = mapped_column(Text)
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    trans_heads: Mapped[list["ThTransHead"]] = relationship(
        back_populates="content", default_factory=list, init=False
    )
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default_factory=lambda: str(uuid.uuid4())
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
    content_id: Mapped[str] = mapped_column(
        Text, ForeignKey("th.content.id", ondelete="CASCADE"), nullable=False
    )
    target_lang: Mapped[str] = mapped_column(Text)
    revision_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(translation_status_enum)
    src_payload_json: Mapped[dict[str, Any]] = mapped_column(json_type)
    variant_key: Mapped[str] = mapped_column(
        Text, server_default="-", default="-", init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default_factory=lambda: str(uuid.uuid4())
    )
    origin_lang: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    translated_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        json_type, nullable=True, default=None
    )
    engine_name: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    engine_version: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
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

    # 无默认值的字段必须在前面
    project_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_id: Mapped[str] = mapped_column(
        Text, ForeignKey("th.content.id", ondelete="CASCADE"), nullable=False
    )
    target_lang: Mapped[str] = mapped_column(Text)
    current_rev_id: Mapped[str] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(translation_status_enum)
    current_no: Mapped[int] = mapped_column(Integer)
    published_rev_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    published_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # 有默认值的主键字段
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default_factory=lambda: str(uuid.uuid4())
    )

    # init=False 字段放在后面
    variant_key: Mapped[str] = mapped_column(
        Text, server_default="-", default="-", init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    content: Mapped["ThContent"] = relationship(
        back_populates="trans_heads", init=False, lazy="select",
        foreign_keys=[content_id]
    )

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
    resolved_rev_id: Mapped[str] = mapped_column(Text)
    resolved_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    variant_key: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default="-", default="-", init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    origin_lang: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

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

    project_id: Mapped[str] = mapped_column(
        ForeignKey("th.projects.project_id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(Text)
    src_lang: Mapped[str] = mapped_column(Text)
    tgt_lang: Mapped[str] = mapped_column(Text)
    src_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    src_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    tgt_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    variant_key: Mapped[str] = mapped_column(
        Text, server_default="-", default="-", init=False
    )
    approved: Mapped[bool] = mapped_column(
        Boolean, server_default="TRUE", default=True, init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default_factory=lambda: str(uuid.uuid4())
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

    project_id: Mapped[str] = mapped_column(Text)
    translation_rev_id: Mapped[str] = mapped_column(Text)
    tm_id: Mapped[str] = mapped_column(ForeignKey("th.tm_units.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default_factory=lambda: str(uuid.uuid4())
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

    __table_args__ = (
        {"schema": "th"},
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )


class ThEvents(Base):
    __tablename__ = "events"

    project_id: Mapped[str] = mapped_column(Text)
    head_id: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        init=False,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        json_type, nullable=True, default=None
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

    project_id: Mapped[str] = mapped_column(Text)
    head_id: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        init=False,
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

    __tablename__ = "outbox"

    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(json_type, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default_factory=uuid.uuid4,
        init=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        server_default="pending",
        index=True,
        nullable=False,
        default="pending",
        init=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        default_factory=lambda: datetime.now(timezone.utc),
        init=False,
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, server_default="0", default=0, init=False
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, server_default="1", default=1, init=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=None
    )
    last_error: Mapped[dict[str, Any] | None] = mapped_column(
        json_type, nullable=True, default=None
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "topic", "event_id", name="ux_outbox_project_topic_event"
        ),
        {"schema": "th"},
    )
