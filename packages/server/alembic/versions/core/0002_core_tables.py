"""
0002_core_tables.py (方言感知版)
职责：projects / content / trans_rev / trans_head（含质量与工作流字段）。
对齐基线：MIGRATION_GUIDE §L1 / 白皮书 v3.0 §6.*
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None

    # 根据方言动态创建 ENUM 类型
    if is_postgres:
        translation_status_enum = postgresql.ENUM(
            "draft",
            "reviewed",
            "published",
            "rejected",
            name="translation_status",
            schema=schema,
            create_type=False,
        )
        workflow_state_enum = postgresql.ENUM(
            "draft",
            "in_review",
            "ready",
            "frozen",
            name="workflow_state",
            schema=schema,
            create_type=False,
        )
    else:
        translation_status_enum = sa.Enum(
            "draft", "reviewed", "published", "rejected", name="translation_status"
        )
        workflow_state_enum = sa.Enum(
            "draft", "in_review", "ready", "frozen", name="workflow_state"
        )

    op.create_table(
        "projects",
        sa.Column("project_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=schema,
    )

    op.create_table(
        "content",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False, comment="UIDA"),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("keys_sha256_bytes", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_lang", sa.Text(), nullable=False),
        sa.Column(
            "source_payload_json",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            server_default=sa.text("'{}'"),
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
            [f"{schema}.projects.project_id" if schema else "projects.project_id"],
            name="fk_content_project_id_projects",
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
        )
        if is_postgres
        else sa.CheckConstraint("1=1"),
        schema=schema,
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
            "src_payload_json",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "translated_payload_json",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=True,
        ),
        sa.Column("engine_name", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("reviewer", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column(
            "checked_rules",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=True,
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
            ["content_id"],
            [f"{schema}.content.id" if schema else "content.id"],
            name="fk_trans_rev_content_id_content",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "id", name="pk_trans_rev"),
        sa.UniqueConstraint(
            "project_id",
            "content_id",
            "target_lang",
            "variant_key",
            "revision_no",
            name="uq_rev_dim",
        ),
        sa.CheckConstraint("th.is_bcp47(target_lang)", name="ck_rev_target_lang_bcp47")
        if is_postgres
        else sa.CheckConstraint("1=1"),
        sa.CheckConstraint(
            "origin_lang IS NULL OR th.is_bcp47(origin_lang)",
            name="ck_rev_origin_lang_bcp47",
        )
        if is_postgres
        else sa.CheckConstraint("1=1"),
        schema=schema,
        postgresql_partition_by="HASH (project_id)" if is_postgres else None,
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
            "workflow_state",
            workflow_state_enum,
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("lock_reason", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("project_id", "id", name="pk_trans_head"),
        sa.ForeignKeyConstraint(
            ["content_id"],
            [f"{schema}.content.id" if schema else "content.id"],
            name="fk_head_content_id_content",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "current_rev_id"],
            [
                f"{schema}.trans_rev.project_id" if schema else "trans_rev.project_id",
                f"{schema}.trans_rev.id" if schema else "trans_rev.id",
            ],
            name="fk_head_current_rev_trans_rev",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "published_rev_id"],
            [
                f"{schema}.trans_rev.project_id" if schema else "trans_rev.project_id",
                f"{schema}.trans_rev.id" if schema else "trans_rev.id",
            ],
            name="fk_head_published_rev_trans_rev",
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
        sa.CheckConstraint("th.is_bcp47(target_lang)", name="ck_head_target_lang_bcp47")
        if is_postgres
        else sa.CheckConstraint("1=1"),
        schema=schema,
        postgresql_partition_by="HASH (project_id)" if is_postgres else None,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None
    op.drop_table("trans_head", schema=schema)
    op.drop_table("trans_rev", schema=schema)
    op.drop_table("content", schema=schema)
    op.drop_table("projects", schema=schema)
