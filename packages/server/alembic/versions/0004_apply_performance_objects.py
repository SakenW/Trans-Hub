# packages/server/alembic/versions/0004_apply_performance_objects.py
"""
迁移 0004: 应用性能优化对象（最终替换版）
- 为 trans_rev/trans_head 创建 HASH 分区子表 (8 片)
- 创建常用索引
- 创建搜索用物化视图 th.search_rev + 索引
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1) 创建 8 片分区
    for i in range(8):
        op.execute(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='th' AND c.relname='trans_rev_p{i}'
          ) THEN
            CREATE TABLE th.trans_rev_p{i} PARTITION OF th.trans_rev
            FOR VALUES WITH (MODULUS 8, REMAINDER {i});
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='th' AND c.relname='trans_head_p{i}'
          ) THEN
            CREATE TABLE th.trans_head_p{i} PARTITION OF th.trans_head
            FOR VALUES WITH (MODULUS 8, REMAINDER {i});
          END IF;
        END$$;
        """)

    # 2) 常用索引
    op.create_index("ix_resolve_expires", "resolve_cache", ["expires_at"], unique=False, schema="th")
    op.create_index("ix_events_head", "events", ["project_id", "head_id"], unique=False, schema="th")
    op.create_index("ix_comments_head", "comments", ["project_id", "head_id"], unique=False, schema="th")
    op.create_index("ix_tm_links_tm_id", "tm_links", ["tm_id"], unique=False, schema="th")

    # 针对 JSONB 的 GIN 索引（用于粗粒度过滤）
    op.create_index("ix_trans_rev_payload_gin", "trans_rev", ["payload"], unique=False, schema="th", postgresql_using="gin")

    # 3) 搜索物化视图
    op.execute("""
    CREATE MATERIALIZED VIEW IF NOT EXISTS th.search_rev AS
    SELECT
      r.project_id,
      r.content_id,
      r.id AS rev_id,
      r.target_lang,
      r.variant_key,
      to_tsvector('simple',
        coalesce((r.payload ->> 'text'), '') || ' ' ||
        coalesce((r.payload ->> 'title'), '')
      ) AS tsv
    FROM th.trans_rev r
    WHERE r.status IN ('reviewed','published');
    """)

    op.create_index(
        "ux_search_rev_ident",
        "search_rev",
        ["project_id", "content_id", "target_lang", "variant_key", "rev_id"],
        unique=True, schema="th"
    )
    op.create_index(
        "ix_search_rev_tsv",
        "search_rev",
        ["tsv"],
        unique=False, schema="th", postgresql_using="gin"
    )

def downgrade() -> None:
    # 1) 物化视图及索引
    op.execute("DROP MATERIALIZED VIEW IF EXISTS th.search_rev CASCADE;")
    op.drop_index("ix_trans_rev_payload_gin", table_name="trans_rev", schema="th")
    op.drop_index("ix_tm_links_tm_id", table_name="tm_links", schema="th")
    op.drop_index("ix_comments_head", table_name="comments", schema="th")
    op.drop_index("ix_events_head", table_name="events", schema="th")
    op.drop_index("ix_resolve_expires", table_name="resolve_cache", schema="th")

    # 2) 分区子表清理（可重复执行）
    for i in range(8):
        op.execute(f"DROP TABLE IF EXISTS th.trans_head_p{i} CASCADE;")
        op.execute(f"DROP TABLE IF EXISTS th.trans_rev_p{i} CASCADE;")
