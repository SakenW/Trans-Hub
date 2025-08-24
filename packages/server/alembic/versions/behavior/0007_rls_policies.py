from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SQL_UP_COMMANDS = [
    r"""CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
DECLARE v TEXT := current_setting('th.allowed_projects', true);
BEGIN
  IF v IS NULL OR btrim(v) = '' THEN
    RETURN ARRAY[]::TEXT[]; -- 默认拒绝更安全
  END IF;
  RETURN string_to_array(regexp_replace(v, '\s+', '', 'g'), ',');
END;
$$;""",
    r"""DO $$
DECLARE
  tables_with_rls TEXT[] := ARRAY[
    'projects','content','trans_rev','trans_head','resolve_cache',
    'events','comments','locales_fallbacks','tm_units','tm_links'
  ];
  t_name TEXT;
BEGIN
  FOREACH t_name IN ARRAY tables_with_rls LOOP
    EXECUTE format('ALTER TABLE th.%I ENABLE ROW LEVEL SECURITY;', t_name);
    EXECUTE format('ALTER TABLE th.%I FORCE ROW LEVEL SECURITY;', t_name);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_rls ON th.%1$s;', t_name);
    EXECUTE format(
      'CREATE POLICY p_%1$s_rls ON th.%1$s FOR ALL TO PUBLIC ' ||
      'USING (project_id = ANY(th.allowed_projects())) ' ||
      'WITH CHECK (project_id = ANY(th.allowed_projects()));',
      t_name
    );
  END LOOP;
END; $$;""",
]

SQL_DOWN_COMMANDS = [
    r"""DO $$
DECLARE
  tables_with_rls TEXT[] := ARRAY[
    'projects','content','trans_rev','trans_head','resolve_cache',
    'events','comments','locales_fallbacks','tm_units','tm_links'
  ];
  t_name TEXT;
BEGIN
  FOREACH t_name IN ARRAY tables_with_rls LOOP
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_rls ON th.%1$s;', t_name);
    EXECUTE format('ALTER TABLE th.%1$s DISABLE ROW LEVEL SECURITY;', t_name);
  END LOOP;
END; $$;""",
    "DROP FUNCTION IF EXISTS th.allowed_projects() CASCADE;",
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
