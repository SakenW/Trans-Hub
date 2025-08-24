from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    now_func = sa.text("now()") if is_postgres else sa.text("(DATETIME('now'))")

    op.create_table(
        "outbox_dead_letter",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("error", json_type, nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=now_func,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_dead_letter"),
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "th" if is_postgres else None
    op.drop_table("outbox_dead_letter", schema=schema)
