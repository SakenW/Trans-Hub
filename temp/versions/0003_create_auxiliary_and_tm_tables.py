# packages/server/alembic/versions/0003_create_auxiliary_and_tm_tables.py
"""
迁移 0003: 扩展功能表 (最终完整版)

职责:
- 创建所有辅助表和 TM 相关表，并包含所有数据完整性 CHECK 约束。
  - th.resolve_cache
  - th.events
  - th.comments
  - th.locales_fallbacks
  - th.tm_units
  - th.tm_links

Revision ID: 0003
Revises: 0002
Create Date: 2025-08-17 16:02:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === th.resolve_cache ===
    op.create_table(
        "resolve_cache",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column("resolved_rev_id", sa.Text(), nullable=False),
        sa.Column(
            "resolved_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("origin_lang", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["th.projects.project_id"],
            name=op.f("fk_resolve_cache_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["th.content.id"],
            name=op.f("fk_resolve_cache_content_id_content"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "resolved_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            name=op.f("fk_resolve_cache_rev_id_trans_rev"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id",
            "content_id",
            "target_lang",
            "variant_key",
            name=op.f("pk_resolve_cache"),
        ),
        # [补丁] 添加 CHECK 约束
        sa.CheckConstraint(
            "th.is_bcp47(target_lang)", name="ck_cache_target_lang_bcp47"
        ),
        sa.CheckConstraint(
            "origin_lang IS NULL OR th.is_bcp47(origin_lang)",
            name="ck_cache_origin_lang_bcp47",
        ),
        schema="th",
    )

    # === th.events (无变化) ===
    op.create_table(
        "events",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(), nullable=False, primary_key=True
        ),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column(
            "actor", sa.Text(), server_default=sa.text("'system'"), nullable=False
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            name=op.f("fk_events_head_id_trans_head"),
            ondelete="CASCADE",
        ),
        schema="th",
    )

    # === th.comments (无变化) ===
    op.create_table(
        "comments",
        sa.Column(
            "id", sa.BigInteger(), sa.Identity(), nullable=False, primary_key=True
        ),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            name=op.f("fk_comments_head_id_trans_head"),
            ondelete="CASCADE",
        ),
        schema="th",
    )

    # === th.locales_fallbacks ===
    op.create_table(
        "locales_fallbacks",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column(
            "fallback_order", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["th.projects.project_id"],
            name=op.f("fk_locales_fallbacks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "locale", name=op.f("pk_locales_fallbacks")
        ),
        # [补丁] 添加 CHECK 约束
        sa.CheckConstraint("th.is_bcp47(locale)", name="ck_locales_fallbacks_bcp47"),
        schema="th",
    )

    # === th.tm_units ===
    op.create_table(
        "tm_units",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("src_lang", sa.Text(), nullable=False),
        sa.Column("tgt_lang", sa.Text(), nullable=False),
        sa.Column("src_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "src_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "tgt_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column(
            "approved", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["th.projects.project_id"],
            name=op.f("fk_tm_units_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id",
            "namespace",
            "src_hash",
            "tgt_lang",
            "variant_key",
            name="uq_tm_units_dim",
        ),
        # [补丁] 添加 CHECK 约束
        sa.CheckConstraint(
            "octet_length(src_hash) = 32", name="ck_tm_units_src_hash_len"
        ),
        sa.CheckConstraint("th.is_bcp47(src_lang)", name="ck_tm_src_lang_bcp47"),
        sa.CheckConstraint("th.is_bcp47(tgt_lang)", name="ck_tm_tgt_lang_bcp47"),
        schema="th",
    )

    # === th.tm_links (无变化) ===
    op.create_table(
        "tm_links",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("translation_rev_id", sa.Text(), nullable=False),
        sa.Column("tm_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "translation_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            name=op.f("fk_tm_links_rev_id_trans_rev"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tm_id"],
            ["th.tm_units.id"],
            name=op.f("fk_tm_links_tm_id_tm_units"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"
        ),
        schema="th",
    )


def downgrade() -> None:
    """回滚此迁移。"""
    op.drop_table("tm_links", schema="th")
    op.drop_table("tm_units", schema="th")
    op.drop_table("locales_fallbacks", schema="th")
    op.drop_table("comments", schema="th")
    op.drop_table("events", schema="th")
    op.drop_table("resolve_cache", schema="th")
