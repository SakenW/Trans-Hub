# packages/server/alembic/versions/platform/0010_outbox_dlq.py
"""
L4-platform-deadletter-0010_outbox_dlq.py
职责：死信队列（JSONB error + project_id）。
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0010_outbox_dlq"
down_revision = "0009_rls_outbox_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_dead_letter",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_dead_letter"),
        schema="th",
    )


def downgrade() -> None:
    op.drop_table("outbox_dead_letter", schema="th")
