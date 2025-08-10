# trans_hub/db/schema.py
# [v2.4.3 Final Sync] ORM 模型与 3f8b9e6a0c2c Alembic 迁移脚本完全对齐。
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import TypeEngine

# 定义 ENUM 类型以供 ORM 使用
translation_status_enum = Enum(
    "draft", "reviewed", "published", "rejected", name="translation_status"
)


def _json_type(dialect_name: str) -> TypeEngine[Any]:
    """根据方言选择 JSON 或 JSONB。"""
    if dialect_name == "postgresql":
        return JSON()  # 返回JSON类型的实例而不是类型本身
    return JSON()


class Base(DeclarativeBase):
    """自定义的声明式基类，提供方言相关的便利属性。"""

    @property
    def _dialect_name(self) -> str:
        # 直接返回默认方言，避免访问可能不存在的bind属性
        return "postgresql"

    @property
    def json_type(self) -> TypeEngine[Any]:
        return _json_type(self._dialect_name)


class ThProjects(Base):
    """项目集中注册表"""

    __tablename__ = "th_projects"
    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    platform: Mapped[str | None] = mapped_column(String)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ThContent(Base):
    """源内容权威表"""

    __tablename__ = "th_content"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th_projects.project_id"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    keys_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    keys_b64: Mapped[str] = mapped_column(Text, nullable=False)
    keys_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
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
        UniqueConstraint(
            "project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"
        ),
    )


class ThTransRev(Base):
    """翻译修订历史表 (Append-only)"""

    __tablename__ = "th_trans_rev"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th_projects.project_id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False
    )
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
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th_projects.project_id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False
    )
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, server_default="-")
    current_rev_id: Mapped[str] = mapped_column(String, nullable=False)
    current_status: Mapped[str] = mapped_column(translation_status_enum, nullable=False)
    current_no: Mapped[int] = mapped_column(Integer, nullable=False)
    published_rev_id: Mapped[str | None] = mapped_column(String)
    published_no: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
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
            ["th_trans_rev.project_id", "th_trans_rev.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "published_rev_id"],
            ["th_trans_rev.project_id", "th_trans_rev.id"],
        ),
    )


class SearchContent(Base):
    """影子索引表"""

    __tablename__ = "search_content"
    content_id: Mapped[str] = mapped_column(
        ForeignKey("th_content.id", ondelete="CASCADE"), primary_key=True
    )


class ThTm(Base):
    """翻译记忆库"""

    __tablename__ = "th_tm"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    namespace: Mapped[str] = mapped_column(String, nullable=False)
    reuse_sha256_bytes: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    source_text_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    translated_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    variant_key: Mapped[str] = mapped_column(String, nullable=False, server_default="-")
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    visibility_scope: Mapped[str] = mapped_column(
        String, nullable=False, server_default="project"
    )
    policy_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    hash_algo_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    reuse_policy_fingerprint: Mapped[str | None] = mapped_column(String)
    quality_score: Mapped[float | None] = mapped_column(Float)
    pii_flags: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    )


class ThTmLinks(Base):
    """复用追溯"""

    __tablename__ = "th_tm_links"
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    translation_rev_id: Mapped[str] = mapped_column(String, nullable=False)
    tm_id: Mapped[str] = mapped_column(
        ForeignKey("th_tm.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"
        ),
        ForeignKeyConstraint(
            ["project_id", "translation_rev_id"],
            ["th_trans_rev.project_id", "th_trans_rev.id"],
            name="fk_tm_links_rev",
            ondelete="CASCADE",
        ),
    )


class ThLocalesFallbacks(Base):
    """语言回退策略"""

    __tablename__ = "th_locales_fallbacks"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("th_projects.project_id"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String, primary_key=True)
    fallback_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ThResolveCache(Base):
    """运行时解析缓存"""

    __tablename__ = "th_resolve_cache"
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    content_id: Mapped[str] = mapped_column(String, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String, primary_key=True)
    variant_key: Mapped[str] = mapped_column(String, primary_key=True)
    resolved_rev: Mapped[str] = mapped_column(String, nullable=False)
    origin_lang: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
