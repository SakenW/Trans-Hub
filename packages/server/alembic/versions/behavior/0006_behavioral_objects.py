"""
0006_behavioral_objects.py
职责：事件/缓存函数、触发器挂载、兼容视图（频道名支持 GUC）。
对齐基线：MIGRATION_GUIDE §L3 / 白皮书 v3.0 §6.*
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SQL_UP_COMMANDS = [
    r"""CREATE OR REPLACE FUNCTION th.emit_event(
      p_project_id TEXT, p_head_id TEXT, p_event TEXT,
      p_payload JSONB DEFAULT '{}'::jsonb, p_actor TEXT DEFAULT 'system',
      p_severity th.event_severity DEFAULT 'info'
    ) RETURNS VOID LANGUAGE sql AS $$
      INSERT INTO th.events(project_id, head_id, event_type, payload, actor, severity, headline)
      VALUES (p_project_id, p_head_id, p_event, coalesce(p_payload,'{}'::jsonb), p_actor, p_severity, NULL);
    $$;""",
    r"""CREATE OR REPLACE FUNCTION th.invalidate_resolve_cache_for_head(
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
    $$;""",
    r"""CREATE OR REPLACE FUNCTION th.on_head_publish_unpublish()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE
      v_event TEXT;
      v_deleted INTEGER;
      v_channel TEXT := coalesce(current_setting('th.notify_channel', true), 'th_cache_invalidation');
    BEGIN
      IF TG_OP = 'UPDATE' AND OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id THEN
        v_event := CASE WHEN NEW.published_rev_id IS NULL THEN 'unpublished' ELSE 'published' END;
        PERFORM th.emit_event(
          NEW.project_id, NEW.id, v_event,
          jsonb_build_object('old_rev', OLD.published_rev_id, 'new_rev', NEW.published_rev_id, 'content_id', NEW.content_id),
          'system', 'info'
        );
        v_deleted := th.invalidate_resolve_cache_for_head(
          NEW.project_id, NEW.content_id, NEW.target_lang, NEW.variant_key
        );
        PERFORM pg_notify(
          v_channel,
          jsonb_build_object('event', v_event, 'content_id', NEW.content_id, 'deleted_cache_entries', v_deleted)::text
        );
      END IF;
      RETURN NEW;
    END;
    $$;""",
    "CREATE OR REPLACE TRIGGER trg_forbid_content_uida_update BEFORE UPDATE ON th.content FOR EACH ROW EXECUTE FUNCTION th.forbid_uida_update();",
    r"""DO $$
    DECLARE t_name TEXT;
    BEGIN
      FOR t_name IN SELECT table_name FROM information_schema.tables
        WHERE table_schema='th' AND table_name IN ('content','trans_rev','trans_head','resolve_cache','tm_units','locales_fallbacks')
      LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_updated_at BEFORE UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();', t_name);
      END LOOP;
      FOR t_name IN SELECT table_name FROM information_schema.tables
        WHERE table_schema='th' AND table_name IN ('trans_rev','trans_head','resolve_cache')
      LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_variant_norm BEFORE INSERT OR UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.variant_normalize();', t_name);
      END LOOP;
    END $$;""",
    r"""CREATE OR REPLACE TRIGGER trg_head_publish_unpublish
    AFTER UPDATE OF published_rev_id ON th.trans_head
    FOR EACH ROW WHEN (OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id)
    EXECUTE FUNCTION th.on_head_publish_unpublish();""",
    r"""CREATE OR REPLACE FUNCTION th._on_head_set_published_at()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' AND NEW.published_rev_id IS DISTINCT FROM OLD.published_rev_id THEN
        IF NEW.published_rev_id IS NULL THEN
          NEW.published_at := NULL;
        ELSE
          NEW.published_at := now();
        END IF;
      END IF;
      RETURN NEW;
    END; $$;""",
    "DROP TRIGGER IF EXISTS trg_head_set_published_at ON th.trans_head;",
    r"""CREATE TRIGGER trg_head_set_published_at
    BEFORE UPDATE OF published_rev_id ON th.trans_head
    FOR EACH ROW EXECUTE FUNCTION th._on_head_set_published_at();""",
    "CREATE OR REPLACE VIEW public.th_projects AS SELECT * FROM th.projects;",
    "CREATE OR REPLACE VIEW public.th_content AS SELECT * FROM th.content;",
    "CREATE OR REPLACE VIEW public.th_trans_rev AS SELECT * FROM th.trans_rev;",
    "CREATE OR REPLACE VIEW public.th_trans_head AS SELECT * FROM th.trans_head;",
    "CREATE OR REPLACE VIEW public.th_resolve_cache AS SELECT * FROM th.resolve_cache;",
    "CREATE OR REPLACE VIEW public.th_events AS SELECT * FROM th.events;",
    "CREATE OR REPLACE VIEW public.th_comments AS SELECT * FROM th.comments;",
    "CREATE OR REPLACE VIEW public.th_tm_units AS SELECT * FROM th.tm_units;",
    "CREATE OR REPLACE VIEW public.th_tm_links AS SELECT * FROM th.tm_links;",
    "CREATE OR REPLACE VIEW public.th_locales_fallbacks AS SELECT * FROM th.locales_fallbacks;",
]

SQL_DOWN_COMMANDS = [
    "DROP VIEW IF EXISTS public.th_locales_fallbacks;",
    "DROP VIEW IF EXISTS public.th_tm_links;",
    "DROP VIEW IF EXISTS public.th_tm_units;",
    "DROP VIEW IF EXISTS public.th_comments;",
    "DROP VIEW IF EXISTS public.th_events;",
    "DROP VIEW IF EXISTS public.th_resolve_cache;",
    "DROP VIEW IF EXISTS public.th_trans_head;",
    "DROP VIEW IF EXISTS public.th_trans_rev;",
    "DROP VIEW IF EXISTS public.th_content;",
    "DROP VIEW IF EXISTS public.th_projects;",
    "DROP TRIGGER IF EXISTS trg_head_set_published_at ON th.trans_head;",
    "DROP FUNCTION IF EXISTS th._on_head_set_published_at() CASCADE;",
    "DROP TRIGGER IF EXISTS trg_head_publish_unpublish ON th.trans_head;",
    "DROP FUNCTION IF EXISTS th.on_head_publish_unpublish() CASCADE;",
    "DROP FUNCTION IF EXISTS th.invalidate_resolve_cache_for_head(TEXT, TEXT, TEXT, TEXT) CASCADE;",
    "DROP FUNCTION IF EXISTS th.emit_event(TEXT, TEXT, TEXT, JSONB, TEXT, th.event_severity) CASCADE;",
    "DROP TRIGGER IF EXISTS trg_forbid_content_uida_update ON th.content;",
    r"""DO $$
    DECLARE t_name TEXT;
    BEGIN
      FOR t_name IN SELECT table_name FROM information_schema.tables
        WHERE table_schema='th' AND table_name IN ('content','trans_rev','trans_head','resolve_cache','tm_units','locales_fallbacks')
      LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_updated_at ON th.%1$s;', t_name);
      END LOOP;
      FOR t_name IN SELECT table_name FROM information_schema.tables
        WHERE table_schema='th' AND table_name IN ('trans_rev','trans_head','resolve_cache')
      LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%1$s_variant_norm ON th.%1$s;', t_name);
      END LOOP;
    END $$;""",
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
