from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SQL_UP_COMMANDS = [
    "ALTER TABLE th.outbox ENABLE ROW LEVEL SECURITY;",
    "ALTER TABLE th.outbox FORCE ROW LEVEL SECURITY;",
    "DROP POLICY IF EXISTS p_outbox_rls ON th.outbox;",
    """CREATE POLICY p_outbox_rls ON th.outbox
FOR ALL TO PUBLIC
USING (project_id = ANY(th.allowed_projects()))
WITH CHECK (project_id = ANY(th.allowed_projects()));""",
]

SQL_DOWN_COMMANDS = [
    "DROP POLICY IF EXISTS p_outbox_rls ON th.outbox;",
    "ALTER TABLE th.outbox DISABLE ROW LEVEL SECURITY;",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for command in SQL_UP_COMMANDS:
        op.execute(command)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for command in SQL_DOWN_COMMANDS:
        op.execute(command)
