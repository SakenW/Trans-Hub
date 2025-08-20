"""
L1-core-tables-0003_aux_tm_tables.py
职责：resolve_cache/events/comments/locales_fallbacks/tm_units/tm_links（加强版）。
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_aux_tm_tables"
down_revision = "0002_core_tables"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # resolve_cache
    op.create_table(
        "resolve_cache",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column("resolved_rev_id", sa.Text(), nullable=False),
        sa.Column("resolved_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("origin_lang", sa.Text(), nullable=True),
        sa.Column("cache_scope", sa.Text(), server_default=sa.text("'global'"), nullable=False),
        sa.Column("build_rev_id", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["th.projects.project_id"], name="fk_resolve_cache_project_id_projects"),
        sa.ForeignKeyConstraint(["content_id"], ["th.content.id"], name="fk_resolve_cache_content_id_content", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id","resolved_rev_id"], ["th.trans_rev.project_id","th.trans_rev.id"], name="fk_resolve_cache_rev_id_trans_rev", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id","content_id","target_lang","variant_key", name="pk_resolve_cache"),
        sa.CheckConstraint("th.is_bcp47(target_lang)", name="ck_cache_target_lang_bcp47"),
        sa.CheckConstraint("origin_lang IS NULL OR th.is_bcp47(origin_lang)", name="ck_cache_origin_lang_bcp47"),
        schema="th",
    )

    # events
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), server_default=sa.text("'system'"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Enum("info","warn","error", name="event_severity", schema="th", create_type=False), server_default=sa.text("'info'"), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id","head_id"], ["th.trans_head.project_id","th.trans_head.id"], name="fk_events_head_id_trans_head", ondelete="CASCADE"),
        schema="th",
    )

    # comments（线程、自引用、锚点、可选绑定具体 rev）
    op.create_table(
        "comments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column("rev_id", sa.Text(), nullable=True, comment="可选：具体 revision"),
        sa.Column("parent_id", sa.BigInteger(), nullable=True, comment="自引用父评论"),
        sa.Column("anchor_path", sa.Text(), nullable=True, comment="JSON 锚点路径，如 title.main"),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id","head_id"], ["th.trans_head.project_id","th.trans_head.id"], name="fk_comments_head_id_trans_head", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id","rev_id"], ["th.trans_rev.project_id","th.trans_rev.id"], name="fk_comments_rev_id_trans_rev", ondelete="SET NULL"),
        schema="th",
    )
    op.execute("""
    ALTER TABLE th.comments
      ADD CONSTRAINT fk_comments_parent
      FOREIGN KEY (parent_id) REFERENCES th.comments(id)
      ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
    """)
    op.execute("""
    ALTER TABLE th.comments
      ADD CONSTRAINT ck_comments_parent_not_self CHECK (parent_id IS NULL OR parent_id <> id);
    """)

    # locales_fallbacks + 质量校验
    op.create_table(
        "locales_fallbacks",
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("fallback_order", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["th.projects.project_id"], name="fk_locales_fallbacks_project_id_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id","locale", name="pk_locales_fallbacks"),
        sa.CheckConstraint("th.is_bcp47(locale)", name="ck_locales_fallbacks_bcp47"),
        schema="th",
    )
    op.execute("ALTER TABLE th.locales_fallbacks ADD CONSTRAINT ck_locales_fallbacks_is_array CHECK (jsonb_typeof(fallback_order)='array');")
    op.execute(r"""
    CREATE OR REPLACE FUNCTION th._validate_locales_fallbacks()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    DECLARE v_elem TEXT; v_seen TEXT[] := ARRAY[]::TEXT[]; v_locale TEXT := NEW.locale;
    BEGIN
      FOR v_elem IN SELECT x::text FROM jsonb_array_elements_text(NEW.fallback_order) t(x)
      LOOP
        IF v_elem = v_locale THEN RAISE EXCEPTION 'fallback_order contains self (%)', v_locale; END IF;
        IF v_elem = ANY(v_seen) THEN RAISE EXCEPTION 'fallback_order contains duplicates (%)', v_elem; END IF;
        v_seen := array_append(v_seen, v_elem);
      END LOOP;
      WITH RECURSIVE walk(locale, nxt) AS (
        SELECT v_locale::text, v_locale::text
        UNION ALL
        SELECT w.locale, x::text
        FROM walk w
        JOIN th.locales_fallbacks lf ON lf.project_id = NEW.project_id AND lf.locale = w.nxt
        CROSS JOIN LATERAL jsonb_array_elements_text(lf.fallback_order) t(x)
      )
      SELECT 1 FROM walk WHERE nxt = v_locale AND locale <> nxt LIMIT 1 INTO v_elem;
      IF v_elem IS NOT NULL THEN
        RAISE EXCEPTION 'fallback graph has cycle for project % and locale %', NEW.project_id, NEW.locale;
      END IF;
      RETURN NEW;
    END; $$;
    DROP TRIGGER IF EXISTS trg_validate_locales_fallbacks ON th.locales_fallbacks;
    CREATE TRIGGER trg_validate_locales_fallbacks BEFORE INSERT OR UPDATE ON th.locales_fallbacks
    FOR EACH ROW EXECUTE FUNCTION th._validate_locales_fallbacks();
    """)

    # tm_units / tm_links
    op.create_table(
        "tm_units",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("src_lang", sa.Text(), nullable=False),
        sa.Column("tgt_lang", sa.Text(), nullable=False),
        sa.Column("src_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("src_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tgt_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("variant_key", sa.Text(), server_default="-", nullable=False),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("context_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_score", sa.Numeric(5,2), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["th.projects.project_id"], name="fk_tm_units_project_id_projects", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id","namespace","src_hash","tgt_lang","variant_key", name="uq_tm_units_dim"),
        sa.CheckConstraint("octet_length(src_hash)=32", name="ck_tm_units_src_hash_len"),
        sa.CheckConstraint("th.is_bcp47(src_lang)", name="ck_tm_src_lang_bcp47"),
        sa.CheckConstraint("th.is_bcp47(tgt_lang)", name="ck_tm_tgt_lang_bcp47"),
        schema="th",
    )
    op.execute("ALTER TABLE th.tm_units ADD CONSTRAINT ck_tm_units_context_tags_is_array CHECK (context_tags IS NULL OR jsonb_typeof(context_tags)='array');")

    op.create_table(
        "tm_links",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("translation_rev_id", sa.Text(), nullable=False),
        sa.Column("tm_id", sa.Text(), nullable=False),
        sa.Column("src_span", sa.Text(), nullable=True),
        sa.Column("tgt_span", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id","translation_rev_id"], ["th.trans_rev.project_id","th.trans_rev.id"], name="fk_tm_links_rev_id_trans_rev", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tm_id"], ["th.tm_units.id"], name="fk_tm_links_tm_id_tm_units", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id","translation_rev_id","tm_id", name="uq_tm_links_triplet"),
        schema="th",
    )

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_validate_locales_fallbacks ON th.locales_fallbacks;")
    op.execute("DROP FUNCTION IF EXISTS th._validate_locales_fallbacks() CASCADE;")
    op.drop_table("tm_links", schema="th")
    op.drop_table("tm_units", schema="th")
    op.drop_table("locales_fallbacks", schema="th")
    op.drop_table("comments", schema="th")
    op.drop_table("events", schema="th")
    op.drop_table("resolve_cache", schema="th")
