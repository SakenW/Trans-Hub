# packages/server/alembic/versions/0005_apply_behavioral_objects.py
"""
迁移 0005: 应用行为层对象

职责:
- 创建所有触发器
- 创建 RLS 函数和策略
- 创建兼容性视图

Revision ID: 0005
Revises: 0004
Create Date: 2025-08-17 16:04:00.000000
"""
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

SQL_UP = """
-- 触发器
CREATE OR REPLACE TRIGGER trg_forbid_content_uida_update BEFORE UPDATE ON th.content FOR EACH ROW EXECUTE FUNCTION th.forbid_uida_update();
DO $$
DECLARE t_name TEXT;
BEGIN
  FOR t_name IN SELECT table_name FROM information_schema.tables WHERE table_schema='th' AND table_name IN ('content','trans_rev','trans_head','resolve_cache','tm_units','locales_fallbacks') LOOP
    EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();', t_name);
  END LOOP;
  FOR t_name IN SELECT table_name FROM information_schema.tables WHERE table_schema='th' AND table_name IN ('trans_rev','trans_head','resolve_cache') LOOP
    EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_variant_norm BEFORE INSERT OR UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.variant_normalize();', t_name);
  END LOOP;
END $$;
CREATE OR REPLACE FUNCTION th.on_head_publish_unpublish() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_event TEXT; v_deleted INTEGER;
BEGIN
  IF TG_OP='UPDATE' AND OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id THEN
    v_event := CASE WHEN NEW.published_rev_id IS NULL THEN 'unpublished' ELSE 'published' END;
    INSERT INTO th.events(project_id, head_id, event_type, payload, actor)
    VALUES (NEW.project_id, NEW.id, v_event, jsonb_build_object('old_rev', OLD.published_rev_id, 'new_rev', NEW.published_rev_id, 'content_id', NEW.content_id), 'system');
    DELETE FROM th.resolve_cache WHERE project_id=NEW.project_id AND content_id=NEW.content_id AND target_lang=NEW.target_lang AND variant_key=NEW.variant_key;
  END IF;
  RETURN NEW;
END; $$;
CREATE OR REPLACE TRIGGER trg_head_publish_unpublish AFTER UPDATE OF published_rev_id ON th.trans_head FOR EACH ROW WHEN (OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id) EXECUTE FUNCTION th.on_head_publish_unpublish();

-- RLS
CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
DECLARE v TEXT := current_setting('th.allowed_projects', true);
BEGIN IF v IS NULL OR v = '' THEN RETURN ARRAY[]::TEXT[]; END IF; RETURN string_to_array(regexp_replace(v, '\\s+', '', 'g'), ','); END;
$$;
DO $$
DECLARE t_name TEXT;
BEGIN
  FOR t_name IN SELECT t.tablename FROM pg_tables t JOIN information_schema.columns c ON c.table_schema=t.schemaname AND c.table_name=t.tablename WHERE t.schemaname = 'th' AND c.column_name = 'project_id' AND t.tablename <> 'search_rev' LOOP
    EXECUTE format('ALTER TABLE th.%I ENABLE ROW LEVEL SECURITY;', t_name);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_rls ON th.%1$s;', t_name);
    EXECUTE format('CREATE POLICY p_%1$s_rls ON th.%1$s FOR ALL TO PUBLIC USING (cardinality(th.allowed_projects()) = 0 OR project_id = ANY(th.allowed_projects())) WITH CHECK (cardinality(th.allowed_projects()) = 0 OR project_id = ANY(th.allowed_projects()));', t_name);
    EXECUTE format('ALTER TABLE th.%I FORCE ROW LEVEL SECURITY;', t_name);
  END LOOP;
END; $$;

-- 兼容性视图
CREATE OR REPLACE VIEW public.th_projects AS SELECT * FROM th.projects;
CREATE OR REPLACE VIEW public.th_content AS SELECT * FROM th.content;
CREATE OR REPLACE VIEW public.th_trans_rev AS SELECT * FROM th.trans_rev;
CREATE OR REPLACE VIEW public.th_trans_head AS SELECT * FROM th.trans_head;
CREATE OR REPLACE VIEW public.th_resolve_cache AS SELECT * FROM th.resolve_cache;
CREATE OR REPLACE VIEW public.th_events AS SELECT * FROM th.events;
CREATE OR REPLACE VIEW public.th_comments AS SELECT * FROM th.comments;
CREATE OR REPLACE VIEW public.th_tm_units AS SELECT * FROM th.tm_units;
CREATE OR REPLACE VIEW public.th_tm_links AS SELECT * FROM th.tm_links;
CREATE OR REPLACE VIEW public.th_locales_fallbacks AS SELECT * FROM th.locales_fallbacks;
"""

# [最终修复] 提供一个完整的、顺序正确的 downgrade 脚本
SQL_DOWN = """
-- 1. 删除所有依赖于表的视图
DROP VIEW IF EXISTS public.th_locales_fallbacks;
DROP VIEW IF EXISTS public.th_tm_links;
DROP VIEW IF EXISTS public.th_tm_units;
DROP VIEW IF EXISTS public.th_comments;
DROP VIEW IF EXISTS public.th_events;
DROP VIEW IF EXISTS public.th_resolve_cache;
DROP VIEW IF EXISTS public.th_trans_head;
DROP VIEW IF EXISTS public.th_trans_rev;
DROP VIEW IF EXISTS public.th_content;
DROP VIEW IF EXISTS public.th_projects;

-- 2. 删除 RLS 策略和函数
-- Alembic 会在事务中运行，所以我们不需要手动禁用 RLS
DROP FUNCTION IF EXISTS th.allowed_projects() CASCADE;
-- RLS 策略会随着表的删除而自动消失，但为了清晰，可以显式 drop

-- 3. 删除触发器和它们依赖的函数
DROP TRIGGER IF EXISTS trg_head_publish_unpublish ON th.trans_head;
DROP FUNCTION IF EXISTS th.on_head_publish_unpublish() CASCADE;
-- 其他触发器会随表删除，无需显式 drop
"""

def upgrade() -> None:
    op.execute(SQL_UP)

def downgrade() -> None:
    op.execute(SQL_DOWN)