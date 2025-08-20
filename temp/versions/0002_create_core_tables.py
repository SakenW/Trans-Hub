# packages/server/alembic/versions/0002_create_core_tables.py
"""
迁移 0002: 构建核心表 (最终正确版)

职责:
- 创建与 ORM 模型完全一致的核心表：
  - th.projects
  - th.content
  - th.trans_rev
  - th.trans_head

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

translation_status_enum = postgresql.ENUM(
    "draft",
    "reviewed",
    "published",
    "rejected",
    name="translation_status",
    schema="th",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.Text(), nullable=False, comment="多租户唯一ID"),
        sa.Column("display_name", sa.Text(), nullable=False, comment="展示名"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="启用",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_projects")),
        schema="th",
    )

    op.create_table(
        "content",
        sa.Column("id", sa.Text(), nullable=False, primary_key=True, comment="UIDA"),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("keys_sha256_bytes", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_lang", sa.Text(), nullable=False),
        sa.Column(
            "source_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
            name=op.f("fk_content_project_id_projects"),
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "project_id", "namespace", "keys_sha256_bytes", name="uq_content_ident"
        ),
        sa.CheckConstraint(
            "octet_length(keys_sha256_bytes)=32", name="ck_content_keys_sha256_len"
        ),
        sa.CheckConstraint(
            "th.is_bcp47(source_lang)", name="ck_content_source_lang_bcp47"
        ),
        schema="th",
    )

    op.create_table(
        "trans_rev",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("status", translation_status_enum, nullable=False),
        sa.Column("origin_lang", sa.Text(), nullable=True),
        sa.Column(
            "src_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "translated_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("engine_name", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=True),
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
            ["content_id"],
            ["th.content.id"],
            name=op.f("fk_trans_rev_content_id_content"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "id", name=op.f("pk_trans_rev")),
        sa.UniqueConstraint(
            "project_id",
            "content_id",
            "target_lang",
            "variant_key",
            "revision_no",
            name="uq_rev_dim",
        ),
        sa.CheckConstraint("th.is_bcp47(target_lang)", name="ck_rev_target_lang_bcp47"),
        sa.CheckConstraint(
            "origin_lang IS NULL OR th.is_bcp47(origin_lang)",
            name="ck_rev_origin_lang_bcp47",
        ),
        schema="th",
        postgresql_partition_by="HASH (project_id)",
    )

    op.create_table(
        "trans_head",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column("current_rev_id", sa.Text(), nullable=False),
        sa.Column("current_status", translation_status_enum, nullable=False),
        sa.Column("current_no", sa.Integer(), nullable=False),
        sa.Column("published_rev_id", sa.Text(), nullable=True),
        sa.Column("published_no", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("project_id", "id", name=op.f("pk_trans_head")),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["th.content.id"],
            name=op.f("fk_head_content_id_content"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "current_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            name=op.f("fk_head_current_rev_trans_rev"),
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "published_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            name=op.f("fk_head_published_rev_trans_rev"),
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"
        ),
        sa.UniqueConstraint(
            "project_id", "published_rev_id", name="uq_head_published_rev"
        ),
        sa.CheckConstraint(
            "th.is_bcp47(target_lang)", name="ck_head_target_lang_bcp47"
        ),
        schema="th",
        postgresql_partition_by="HASH (project_id)",
    )


def downgrade() -> None:
    op.drop_table("trans_head", schema="th")
    op.drop_table("trans_rev", schema="th")
    op.drop_table("content", schema="th")
    op.drop_table("projects", schema="th")
