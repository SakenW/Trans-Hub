# packages/server/src/trans_hub/infrastructure/db/_schema.py
"""
定义了与数据库 `3f8b9e6a0c2c` Schema 完全对应的 SQLAlchemy ORM 模型。

本文件是数据库结构的“代码表示”，所有持久化操作都通过这些模型进行。
严格遵守《技术宪章》的命名约定（如 `json_type`）。
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

# --- 宪章合规：定义统一的 JSON 类型别名 ---
# 在 PostgreSQL 中使用性能更优的 JSONB，在其他方言中回退到通用的 JSON。
try:
    # 尝试导入PostgreSQL特定的JSONB类型
    json_type = JSONB(astext_type=Text())
except (ImportError, AttributeError):
    # 如果失败（例如，没有安装psycopg2或在非PostgreSQL环境），则使用标准的JSON类型
    json_type = JSON()


class Base(DeclarativeBase):
    """ORM 模型的基类。"""
    pass


# 定义 ENUM 类型以供 ORM 使用
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


class ThProjects(Base):
    """项目注册表 (`th_projects`)"""
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
    """源内容权威表 (`th_content`)"""
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
    """翻译修订历史表 (`th_trans_rev`)"""
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
    """翻译头表 (`th_trans_head`)"""
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

class ThTransEvent(Base):
    """事件日志表 (`th_trans_events`)"""
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
    """评论表 (`th_trans_comments`)"""
    __tablename__ = "th_trans_comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String)
    head_id: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["project_id", "head_id"], ["th_trans_head.project_id", "th_trans_head.id"], ondelete="CASCADE"),)


class ThResolveCache(Base):
    """解析缓存表 (`th_resolve_cache`)"""
    __tablename__ = "th_resolve_cache"
    project_id: Mapped[str] = mapped_column(String)
    content_id: Mapped[str] = mapped_column(String, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String, primary_key=True)
    variant_key: Mapped[str] = mapped_column(String, primary_key=True)
    resolved_rev_id: Mapped[str] = mapped_column(String)
    resolved_payload: Mapped[dict[str, Any]] = mapped_column(json_type)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["project_id", "resolved_rev_id"], ["th_trans_rev.project_id", "th_trans_rev.id"], ondelete="CASCADE"),)