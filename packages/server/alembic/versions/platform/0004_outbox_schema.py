"""
0004_outbox_schema.py (方言感知版)
职责：Outbox 表结构（最优化：表名 th.outbox，复合幂等键，JSONB 错误字段）。
对齐基线：MIGRATION_GUIDE §L4 / 白皮书 v3.0 §7.*
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None

    op.create_table(
        "outbox",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()") if is_postgres else None,
            nullable=False,
        ),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "last_error",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=True,
            comment="结构化错误",
        ),
        sa.Column(
            "schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("event_id", sa.Text(), nullable=False, comment="业务幂等键"),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
        sa.UniqueConstraint(
            "project_id", "topic", "event_id", name="ux_outbox_project_topic_event"
        ),
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None
    op.drop_table("outbox", schema=schema)
