# packages/server/alembic/versions/platform/0009_rls_outbox_policies.py
"""
L4-platform-policies-0009_outbox_policies.py
职责：Outbox RLS（默认拒绝，按 allowed_projects 白名单放行）。
"""

from __future__ import annotations
from alembic import op

# revision identifiers
revision = "0009_rls_outbox_policies"
down_revision = "0008_outbox_indexes"
branch_labels = None
depends_on = None

SQL_UP = r"""
ALTER TABLE th.outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE th.outbox_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_outbox_rls ON th.outbox_events;
CREATE POLICY p_outbox_rls ON th.outbox_events
FOR ALL TO PUBLIC
USING (project_id = ANY(th.allowed_projects()))
WITH CHECK (project_id = ANY(th.allowed_projects()));
"""

SQL_DOWN = r"""
DROP POLICY IF EXISTS p_outbox_rls ON th.outbox_events;
ALTER TABLE th.outbox_events DISABLE ROW LEVEL SECURITY;
"""


def upgrade() -> None:
    op.execute(SQL_UP)


def downgrade() -> None:
    op.execute(SQL_DOWN)
