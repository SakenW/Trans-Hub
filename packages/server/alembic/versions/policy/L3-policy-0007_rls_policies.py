"""
L3-policy-0007_rls_policies.py
职责：allowed_projects() + 统一 RLS（默认拒绝）。
"""
from __future__ import annotations
from alembic import op

revision = "0007_rls_policies"
down_revision = "0006_behavioral_objects"
branch_labels = None
depends_on = None

SQL_UP = r"""
CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
DECLARE v TEXT := current_setting('th.allowed_projects', true);
BEGIN
  IF v IS NULL OR btrim(v) = '' THEN
    RETURN ARRAY[]::TEXT[]; -- 默认拒绝更安全
  END IF;
  RETURN string_to_array(regexp_replace(v, '\s+', '', 'g'), ',');
END;
$$;

DO $$
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
END; $$;
"""

SQL_DOWN = r"""
DO $$
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
END; $$;
DROP FUNCTION IF EXISTS th.allowed_projects() CASCADE;
"""

def upgrade() -> None:
    op.execute(SQL_UP)

def downgrade() -> None:
    op.execute(SQL_DOWN)
