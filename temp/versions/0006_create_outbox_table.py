# packages/server/alembic/versions/0006_create_outbox_table.py
"""
迁移 0006: 创建事务性发件箱表

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        schema="th",
    )
    op.create_index(
        op.f("ix_outbox_events_status"),
        "outbox_events",
        ["status"],
        unique=False,
        schema="th",
    )
    op.create_index(
        op.f("ix_outbox_events_topic"),
        "outbox_events",
        ["topic"],
        unique=False,
        schema="th",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_outbox_events_topic"), table_name="outbox_events", schema="th"
    )
    op.drop_index(
        op.f("ix_outbox_events_status"), table_name="outbox_events", schema="th"
    )
    op.drop_table("outbox_events", schema="th")
