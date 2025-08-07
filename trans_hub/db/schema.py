# trans_hub/db/schema.py
# [核心重构] 使用 SQLAlchemy 定义的数据模型。
# 这是项目数据结构的“唯一真实来源”，取代了所有 .sql 文件。

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, Mapped
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class ThContent(Base):
    __tablename__ = "th_content"
    id: Mapped[str] = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id: Mapped[str] = Column(String, nullable=False, unique=True, index=True)
    source_payload_json: Mapped[dict] = Column(JSON, nullable=False)
    created_at: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ThContexts(Base):
    __tablename__ = "th_contexts"
    id: Mapped[str] = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    context_hash: Mapped[str] = Column(String, nullable=False, unique=True, index=True)
    context_payload_json: Mapped[dict] = Column(JSON, nullable=False)
    created_at: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ThTranslations(Base):
    __tablename__ = "th_translations"
    id: Mapped[str] = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id: Mapped[str] = Column(
        String, ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False
    )
    context_id: Mapped[str | None] = Column(
        String, ForeignKey("th_contexts.id", ondelete="CASCADE")
    )
    lang_code: Mapped[str] = Column(String, nullable=False)
    source_lang: Mapped[str | None] = Column(String)
    status: Mapped[str] = Column(String, nullable=False, default="PENDING")
    translation_payload_json: Mapped[dict | None] = Column(JSON)
    engine: Mapped[str | None] = Column(String)
    engine_version: Mapped[str | None] = Column(String)
    error: Mapped[str | None] = Column(Text)
    created_at: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_updated_at: Mapped[DateTime] = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    __table_args__ = (
        UniqueConstraint("content_id", "context_id", "lang_code", name="uq_translation"),
        Index("idx_translations_status_lang", "status", "lang_code"),
    )


class ThJobs(Base):
    __tablename__ = "th_jobs"
    id: Mapped[str] = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id: Mapped[str] = Column(
        String,
        ForeignKey("th_content.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_requested_at: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False
    )


class ThDeadLetterQueue(Base):
    __tablename__ = "th_dead_letter_queue"
    id: Mapped[int] = Column(Integer, primary_key=True)
    translation_id: Mapped[str | None] = Column(String)
    original_payload_json: Mapped[dict] = Column(JSON, nullable=False)
    context_payload_json: Mapped[dict | None] = Column(JSON)
    target_lang_code: Mapped[str] = Column(String, nullable=False)
    last_error_message: Mapped[str | None] = Column(Text)
    failed_at: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    engine_name: Mapped[str | None] = Column(String)
    engine_version: Mapped[str | None] = Column(String)


# --- [新增] 修正遗漏的 ThAuditLogs 模型 ---
class ThAuditLogs(Base):
    __tablename__ = "th_audit_logs"
    id: Mapped[int] = Column(Integer, primary_key=True)
    event_id: Mapped[str] = Column(String, nullable=False)
    event_type: Mapped[str] = Column(String, nullable=False)
    table_name: Mapped[str] = Column(String, nullable=False)
    record_id: Mapped[str] = Column(String, nullable=False)
    user_id: Mapped[str | None] = Column(String)
    timestamp: Mapped[DateTime] = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details_json: Mapped[dict | None] = Column(JSON)
    __table_args__ = (
        Index("idx_audit_logs_record", "table_name", "record_id"),
    )