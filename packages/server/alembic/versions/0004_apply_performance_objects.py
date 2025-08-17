# packages/server/alembic/versions/0004_apply_performance_objects.py
"""
迁移 0004: 应用性能优化对象

职责:
- 创建分区子表
- 创建所有索引 (使用 op.execute 修复 GIN 索引)
- 创建物化视图

Revision ID: 0004
Revises: 0003
Create Date: 2025-08-17 16:03:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """应用此迁移。"""
    # --- 1. 创建分区子表 ---
    op.execute("""
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

    # --- 2. 创建索引 ---
    op.create_index('ix_resolve_expires', 'resolve_cache', ['expires_at'], unique=False, schema='th')
    op.create_index('ix_events_head', 'events', ['project_id', 'head_id'], unique=False, schema='th')
    op.create_index('ix_comments_head', 'comments', ['project_id', 'head_id'], unique=False, schema='th')
    op.create_index('ix_tm_links_tm_id', 'tm_links', ['project_id', 'tm_id'], unique=False, schema='th')
    
    # [最终修复] 对于复杂的、带操作符类的 GIN 索引，直接使用 op.execute 是最可靠的方式
    op.execute('CREATE INDEX ix_trans_rev_trgm ON th.trans_rev USING gin ((translated_payload_json::text) gin_trgm_ops);')
    
    # --- 3. 创建搜索物化视图及其索引 ---
    op.execute("""
    CREATE MATERIALIZED VIEW th.search_rev AS
    SELECT r.project_id, r.content_id, r.target_lang, r.variant_key, r.id AS rev_id,
           to_tsvector('simple', th.extract_text(r.translated_payload_json)) AS tsv,
           r.updated_at
    FROM th.trans_rev r
    WHERE r.status IN ('reviewed','published');
    """)
    op.create_index('ux_search_rev_ident', 'search_rev', ['project_id', 'content_id', 'target_lang', 'variant_key', 'rev_id'], unique=True, schema='th')
    op.create_index('ix_search_rev_tsv', 'search_rev', ['tsv'], unique=False, schema='th', postgresql_using='gin')


def downgrade() -> None:
    """回滚此迁移。"""
    op.execute("DROP MATERIALIZED VIEW IF EXISTS th.search_rev CASCADE;")
    # 在 downgrade 中，使用 op.drop_index 仍然是安全的
    op.drop_index('ix_trans_rev_trgm', table_name='trans_rev', schema='th')
    op.drop_index('ix_tm_links_tm_id', table_name='tm_links', schema='th')
    op.drop_index('ix_comments_head', table_name='comments', schema='th')
    op.drop_index('ix_events_head', table_name='events', schema='th')
    op.drop_index('ix_resolve_expires', table_name='resolve_cache', schema='th')