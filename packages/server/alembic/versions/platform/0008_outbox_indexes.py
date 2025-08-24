from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_status ON th.outbox (status);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbox_topic_created ON th.outbox (topic, created_at);"
    )
    op.execute(r"""    DO $$ BEGIN
      IF to_regclass('th.ix_outbox_status_next') IS NULL THEN
        CREATE INDEX ix_outbox_status_next ON th.outbox (status, next_attempt_at);
      END IF;
      IF to_regclass('th.ix_outbox_due_partial') IS NULL THEN
        CREATE INDEX ix_outbox_due_partial ON th.outbox (status, next_attempt_at)
        WHERE status IN ('pending','retrying');
      END IF;
    END $$;
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_due_partial;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_status_next;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_topic_created;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_status;")
