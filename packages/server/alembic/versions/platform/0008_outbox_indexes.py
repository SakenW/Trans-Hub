# packages/server/alembic/versions/platform/0008_outbox_indexes.py
"""
L4-platform-indexes-0008_outbox_indexes.py
职责：Outbox 索引（扫描/调度优化，含部分索引）。
"""
from __future__ import annotations
from alembic import op

# revision identifiers
revision = "0008_outbox_indexes"
down_revision = "0007_rls_policies"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_status ON th.outbox_events (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbox_topic_created ON th.outbox_events (topic, created_at);")
    op.execute(r"""
    DO $$ BEGIN
      IF to_regclass('th.ix_outbox_status_next') IS NULL THEN
        CREATE INDEX ix_outbox_status_next ON th.outbox_events (status, next_attempt_at);
      END IF;
      IF to_regclass('th.ix_outbox_due_partial') IS NULL THEN
        CREATE INDEX ix_outbox_due_partial ON th.outbox_events (status, next_attempt_at)
        WHERE status IN ('pending','retrying');
      END IF;
    END $$;
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_due_partial;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_status_next;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_topic_created;")
    op.execute("DROP INDEX IF EXISTS th.ix_outbox_status;")
