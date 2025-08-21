# packages/server/alembic/versions/perf/0005_perf_objects.py
"""
L2-perf-0005_perf_objects.py
职责：分区子表、常用索引、搜索物化视图（WITH NO DATA + 双 TSV 列）。
"""

from __future__ import annotations
from alembic import op

# revision identifiers
revision = "0005_perf_objects"
down_revision = "0004_outbox_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 分区子表
    op.execute(r"""
    DO $$
    DECLARE i INT; r RECORD;
    BEGIN
      FOR i IN 0..7 LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS th.trans_rev_p%1$s PARTITION OF th.trans_rev FOR VALUES WITH (MODULUS 8, REMAINDER %1$s)', i);
        EXECUTE format('CREATE TABLE IF NOT EXISTS th.trans_head_p%1$s PARTITION OF th.trans_head FOR VALUES WITH (MODULUS 8, REMAINDER %1$s)', i);
      END LOOP;
      FOR r IN
        SELECT inhrelid::regclass AS child
        FROM pg_inherits
        WHERE inhparent IN ('th.trans_rev'::regclass, 'th.trans_head'::regclass)
      LOOP
        EXECUTE format('ALTER TABLE %s SET (fillfactor=90, autovacuum_vacuum_scale_factor=0.1)', r.child);
      END LOOP;
    END $$;
    """)

    # 常用索引（幂等）
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resolve_expires ON th.resolve_cache (expires_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_events_head ON th.events (project_id, head_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_head ON th.comments (project_id, head_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_comments_open ON th.comments (project_id, head_id, resolved);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tm_links_tm_id ON th.tm_links (tm_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cache_dim_build ON th.resolve_cache (project_id, content_id, target_lang, variant_key, build_rev_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cache_dim_scope ON th.resolve_cache (project_id, content_id, target_lang, variant_key, cache_scope);"
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trans_rev_trgm ON th.trans_rev USING gin ((translated_payload_json::text) gin_trgm_ops);"
    )

    # 搜索物化视图（WITH NO DATA）
    op.execute(r"""
    CREATE MATERIALIZED VIEW IF NOT EXISTS th.search_rev AS
    SELECT
      r.project_id,
      r.content_id,
      r.target_lang,
      r.variant_key,
      r.id AS rev_id,
      to_tsvector('simple', th.extract_text(r.translated_payload_json)) AS tsv_simple,
      to_tsvector(th.tsv_config_for_bcp47(r.target_lang), th.extract_text(r.translated_payload_json)) AS tsv_lang,
      r.updated_at
    FROM th.trans_rev r
    WHERE r.status IN ('reviewed','published')
    WITH NO DATA;
    """)
    op.execute(r"""
    DO $$ BEGIN
      IF to_regclass('th.ux_search_rev_ident') IS NULL THEN
        CREATE UNIQUE INDEX ux_search_rev_ident ON th.search_rev (project_id, content_id, target_lang, variant_key, rev_id);
      END IF;
      IF to_regclass('th.ix_search_rev_tsv_simple') IS NULL THEN
        CREATE INDEX ix_search_rev_tsv_simple ON th.search_rev USING gin (tsv_simple);
      END IF;
      IF to_regclass('th.ix_search_rev_tsv_lang') IS NULL THEN
        CREATE INDEX ix_search_rev_tsv_lang ON th.search_rev USING gin (tsv_lang);
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS th.search_rev CASCADE;")
    for i in range(8):
        op.execute(f"DROP TABLE IF EXISTS th.trans_head_p{i} CASCADE;")
        op.execute(f"DROP TABLE IF EXISTS th.trans_rev_p{i} CASCADE;")
    op.execute("DROP INDEX IF EXISTS th.ix_cache_dim_scope;")
    op.execute("DROP INDEX IF EXISTS th.ix_cache_dim_build;")
    op.execute("DROP INDEX IF EXISTS th.ix_tm_links_tm_id;")
    op.execute("DROP INDEX IF EXISTS th.ix_comments_open;")
    op.execute("DROP INDEX IF EXISTS th.ix_comments_head;")
    op.execute("DROP INDEX IF EXISTS th.ix_events_head;")
    op.execute("DROP INDEX IF EXISTS th.ix_resolve_expires;")
    op.execute("DROP INDEX IF EXISTS th.ix_trans_rev_trgm;")
