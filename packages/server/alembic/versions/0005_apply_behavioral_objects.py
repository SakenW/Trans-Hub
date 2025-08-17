# packages/server/alembic/versions/0005_apply_behavioral_objects.py
"""
迁移 0005: 应用行为层对象 (最终完整版)

职责:
- 创建所有触发器，并采用模块化、可复用的函数设计。
- 创建 RLS 函数和策略。
- 创建兼容性视图。
- 引入 pg_notify 机制以支持异步刷新。

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
-- 1. 创建模块化的触发器辅助函数
CREATE OR REPLACE FUNCTION th.emit_event(
  p_project_id TEXT, p_head_id TEXT, p_event TEXT,
  p_payload JSONB DEFAULT '{}'::jsonb, p_actor TEXT DEFAULT 'system'
) RETURNS VOID LANGUAGE sql AS $$
  INSERT INTO th.events(project_id, head_id, event_type, payload, actor)
  VALUES (p_project_id, p_head_id, p_event, coalesce(p_payload,'{}'::jsonb), p_actor);
$$;

CREATE OR REPLACE FUNCTION th.invalidate_resolve_cache_for_head(
  p_project_id TEXT, p_content_id TEXT, p_target_lang TEXT, p_variant_key TEXT
) RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE v_count INTEGER;
BEGIN
  DELETE FROM th.resolve_cache
  WHERE project_id = p_project_id
    AND content_id = p_content_id
    AND target_lang = p_target_lang
    AND variant_key = p_variant_key;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

-- 2. 创建主触发器函数 (调用辅助函数)
CREATE OR REPLACE FUNCTION th.on_head_publish_unpublish()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  v_event TEXT;
  v_deleted INTEGER;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id THEN
    v_event := CASE WHEN NEW.published_rev_id IS NULL THEN 'unpublished' ELSE 'published' END;
    PERFORM th.emit_event(
      NEW.project_id, NEW.id, v_event,
      jsonb_build_object('old_rev', OLD.published_rev_id, 'new_rev', NEW.published_rev_id, 'content_id', NEW.content_id)
    );
    v_deleted := th.invalidate_resolve_cache_for_head(
      NEW.project_id, NEW.content_id, NEW.target_lang, NEW.variant_key
    );
    PERFORM pg_notify(
      'th_cache_invalidation',
      jsonb_build_object('event', v_event, 'content_id', NEW.content_id, 'deleted_cache_entries', v_deleted)::text
    );
  END IF;
  RETURN NEW;
END;
$$;

-- 3. 应用所有触发器
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
CREATE OR REPLACE TRIGGER trg_head_publish_unpublish AFTER UPDATE OF published_rev_id ON th.trans_head FOR EACH ROW WHEN (OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id) EXECUTE FUNCTION th.on_head_publish_unpublish();

-- 4. RLS
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

-- 5. 兼容性视图
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
SQL_DOWN = """
-- 按相反顺序、安全地清理对象
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

DROP FUNCTION IF EXISTS th.allowed_projects() CASCADE;
DROP TRIGGER IF EXISTS trg_head_publish_unpublish ON th.trans_head;
DROP FUNCTION IF EXISTS th.on_head_publish_unpublish() CASCADE;
DROP FUNCTION IF EXISTS th.invalidate_resolve_cache_for_head(TEXT, TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS th.emit_event(TEXT, TEXT, TEXT, JSONB, TEXT) CASCADE;
"""

def upgrade() -> None:
    op.execute(SQL_UP)

def downgrade() -> None:
    op.execute(SQL_DOWN)