# trans_hub/db/schema.py
# [类型净化修正版]

import uuid
from datetime import datetime
from typing import Any  # <-- [新增] 导入 Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class ThContent(Base):
    __tablename__ = "th_content"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    business_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )  # <-- [核心修复]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ThContexts(Base):
    __tablename__ = "th_contexts"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    context_hash: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    context_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )  # <-- [核心修复]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ThTranslations(Base):
    __tablename__ = "th_translations"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        String, ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False
    )
    context_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("th_contexts.id", ondelete="CASCADE")
    )
    lang_code: Mapped[str] = mapped_column(String, nullable=False)
    source_lang: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING")
    translation_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )  # <-- [核心修复]
    engine: Mapped[str | None] = mapped_column(String)
    engine_version: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    __table_args__ = (
        UniqueConstraint(
            "content_id", "context_id", "lang_code", name="uq_translation"
        ),
        Index("idx_translations_status_lang", "status", "lang_code"),
    )


class ThJobs(Base):
    __tablename__ = "th_jobs"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("th_content.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ThDeadLetterQueue(Base):
    __tablename__ = "th_dead_letter_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    translation_id: Mapped[str | None] = mapped_column(String)
    original_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )  # <-- [核心修复]
    context_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON
    )  # <-- [核心修复]
    target_lang_code: Mapped[str] = mapped_column(String, nullable=False)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    engine_name: Mapped[str | None] = mapped_column(String)
    engine_version: Mapped[str | None] = mapped_column(String)


class ThAuditLogs(Base):
    __tablename__ = "th_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # <-- [核心修复]
    __table_args__ = (Index("idx_audit_logs_record", "table_name", "record_id"),)
