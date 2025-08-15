# packages/server/alembic/versions/3f8b9e6a0c2c_initial_schema.py
"""
TRANS-HUB 初始架构 (v3.0.0 · 权威重构版 · Alembic 实现)

本迁移脚本实现《TRANS-HUB 统一数据与命名白皮书 v3.0.0》的完整数据库结构。
它是一次性的、原子化的最优实现，包含了所有必要的约束、函数和性能优化。

实现要点 (PostgreSQL 优先):
- `th` 专用 schema。
- 权威函数与类型: `is_bcp47`, `variant_normalize`, `set_updated_at`, `translation_status` ENUM。
- [新增] `forbid_uida_update`: 确保 UIDA 字段不可变的触发器。
- 核心表结构:
  - th.projects: 项目注册表。
  - th.content: 基于 UIDA 的内容表。
  - th.trans_rev: 按 project_id HASH 分区的修订历史表。
  - th.trans_head: 按 project_id HASH 分区的双指针表，含 DEFERRABLE 外键。
  - th.resolve_cache: 零二次查询解析缓存，增加到 content 的级联删除外键。
- 扩展表: `th.events`, `th.comments`, `th.tm_units`, `th.tm_links`, `th.locales_fallbacks`。
- [新增] 分区子表性能优化: 自动设置 `fillfactor=90` 等参数。
- 搜索策略: 基于 `th.search_rev` 物化视图的全文检索和 `pg_trgm` 的模糊搜索。
- 行级安全 (RLS): 基于 `th.allowed_projects()` 的统一多租户隔离策略。
- 触发器逻辑: 自动更新 updated_at, 规范化 variant_key, 发布时精准缓存失效。
- 兼容视图: 在 public schema 中创建核心表的只读视图。

非 PostgreSQL 方言 (如 SQLite):
- 创建等价表与基础约束/索引，省略高级特性。
"""

from __future__ import annotations

from typing import Any
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# --- Alembic 元数据 ---
revision = "3f8b9e6a0c2c"
down_revision = None
branch_labels = None
depends_on = None


# --- 工具函数 ---
def _json_type(dialect_name: str) -> sa.types.TypeEngine:
    """根据数据库方言选择合适的 JSON 类型。"""
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _compact_args(*args: Any) -> tuple[Any, ...]:
    """过滤掉 None 值，以便安全地解包到 Alembic 操作中。"""
    return tuple(arg for arg in args if arg is not None)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    json_type = _json_type(dialect)

    # =====================================================================================
    # 0. PostgreSQL 专有对象 (Schema, 扩展, 函数, 类型)
    # =====================================================================================
    if dialect == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS th;")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

        op.execute(
            """
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='translation_status') THEN
                    CREATE TYPE th.translation_status AS ENUM ('draft','reviewed','published','rejected');
                END IF;
            END $$;
            """
        )

        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.is_bcp47(lang TEXT) RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
            BEGIN RETURN lang IS NOT NULL AND (lang ~ '^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$' OR lang ~ '^x-[A-Za-z0-9-]+$'); END;
            $$;

            CREATE OR REPLACE FUNCTION th.variant_normalize() RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN NEW.variant_key := lower(coalesce(NEW.variant_key, '-')); IF NEW.variant_key = '' THEN NEW.variant_key := '-'; END IF; RETURN NEW; END;
            $$;

            CREATE OR REPLACE FUNCTION th.set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN NEW.updated_at := CURRENT_TIMESTAMP; RETURN NEW; END;
            $$;

            CREATE OR REPLACE FUNCTION th.extract_text(j JSONB) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
            SELECT string_agg(value, ' ') FROM jsonb_each_text(coalesce(j, '{}'::jsonb));
            $$;

            CREATE OR REPLACE FUNCTION th.forbid_uida_update() RETURNS TRIGGER LANGUAGE plpgsql AS $$
            BEGIN
              IF (NEW.project_id, NEW.namespace, NEW.keys_sha256_bytes) IS DISTINCT FROM (OLD.project_id, OLD.namespace, OLD.keys_sha256_bytes) THEN
                RAISE EXCEPTION 'UIDA fields (project_id, namespace, keys_sha256_bytes) are immutable and cannot be changed.';
              END IF;
              RETURN NEW;
            END;
            $$;
            """
        )

    # =====================================================================================
    # 1. 核心表：th.projects 和 th.content
    # =====================================================================================
    op.create_table(
        "projects",
        sa.Column(
            "project_id",
            sa.Text(),
            primary_key=True,
            comment="人类可读项目 ID（不可变）",
        ),
        sa.Column("display_name", sa.Text(), nullable=False, comment="展示名称"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="项目是否启用",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        schema="th",
        comment="项目主表，作为多租户边界",
    )

    op.create_table(
        "content",
        sa.Column(
            "id", sa.Text(), primary_key=True, comment="内容主键（UIDA 映射，全局唯一）"
        ),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey(
                "th.projects.project_id", deferrable=True, initially="DEFERRED"
            ),
            nullable=False,
            comment="归属项目",
        ),
        sa.Column("namespace", sa.Text(), nullable=False, comment="命名空间（功能域）"),
        sa.Column(
            "keys_sha256_bytes",
            sa.LargeBinary(length=32),
            nullable=False,
            comment="规范化 keys JSON 的 SHA-256",
        ),
        sa.Column("source_lang", sa.Text(), nullable=False, comment="源语言（BCP-47）"),
        sa.Column(
            "source_payload_json",
            json_type,
            nullable=False,
            server_default=sa.text(
                "'{}'::jsonb" if dialect == "postgresql" else "'{}'"
            ),
            comment="源内容 JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="更新时间",
        ),
        *_compact_args(
            sa.UniqueConstraint(
                "project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"
            ),
            sa.CheckConstraint(
                "octet_length(keys_sha256_bytes)=32", name="ck_content_sha256_len"
            )
            if dialect == "postgresql"
            else sa.CheckConstraint(
                "length(keys_sha256_bytes)=32", name="ck_content_sha256_len"
            ),
            sa.CheckConstraint(
                "th.is_bcp47(source_lang)", name="ck_content_source_lang_bcp47"
            )
            if dialect == "postgresql"
            else None,
        ),
        schema="th",
        comment="以 Canonical JSON→SHA-256 形成的唯一内容键（UIDA）实体化",
    )
    op.create_index(
        "ix_content_project", "content", ["project_id"], unique=False, schema="th"
    )

    # =====================================================================================
    # 2. 修订与指针表 (th.trans_rev, th.trans_head)
    # =====================================================================================
    if dialect == "postgresql":
        op.execute(
            """
            CREATE TABLE th.trans_rev (
              project_id              TEXT NOT NULL,
              id                      TEXT NOT NULL,
              content_id              TEXT NOT NULL REFERENCES th.content(id) ON DELETE CASCADE,
              target_lang             TEXT NOT NULL CHECK (th.is_bcp47(target_lang)),
              variant_key             TEXT NOT NULL DEFAULT '-',
              revision_no             INTEGER NOT NULL,
              status                  th.translation_status NOT NULL,
              origin_lang             TEXT CHECK (origin_lang IS NULL OR th.is_bcp47(origin_lang)),
              src_payload_json        JSONB NOT NULL,
              translated_payload_json JSONB,
              created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (project_id, id),
              CONSTRAINT uq_rev_dim UNIQUE (project_id, content_id, target_lang, variant_key, revision_no)
            ) PARTITION BY HASH (project_id);
            """
        )
        op.execute(
            """
            CREATE TABLE th.trans_head (
              project_id        TEXT NOT NULL,
              id                TEXT NOT NULL,
              content_id        TEXT NOT NULL REFERENCES th.content(id) ON DELETE CASCADE,
              target_lang       TEXT NOT NULL CHECK (th.is_bcp47(target_lang)),
              variant_key       TEXT NOT NULL DEFAULT '-',
              current_rev_id    TEXT NOT NULL,
              current_status    th.translation_status NOT NULL,
              current_no        INTEGER NOT NULL,
              published_rev_id  TEXT,
              published_no      INTEGER,
              published_at      TIMESTAMPTZ,
              updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (project_id, id),
              CONSTRAINT uq_head_dim UNIQUE (project_id, content_id, target_lang, variant_key),
              CONSTRAINT uq_head_published_rev UNIQUE (project_id, published_rev_id),
              FOREIGN KEY (project_id, current_rev_id) REFERENCES th.trans_rev(project_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
              FOREIGN KEY (project_id, published_rev_id) REFERENCES th.trans_rev(project_id, id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
            ) PARTITION BY HASH (project_id);
            """
        )
        op.execute(
            """
            DO $$ DECLARE i INT; r RECORD; BEGIN
              FOR i IN 0..7 LOOP
                EXECUTE format('CREATE TABLE IF NOT EXISTS th.trans_rev_p%1$s PARTITION OF th.trans_rev FOR VALUES WITH (MODULUS 8, REMAINDER %1$s)', i);
                EXECUTE format('CREATE TABLE IF NOT EXISTS th.trans_head_p%1$s PARTITION OF th.trans_head FOR VALUES WITH (MODULUS 8, REMAINDER %1$s)', i);
              END LOOP;
              FOR r IN SELECT inhrelid::regclass AS child FROM pg_inherits WHERE inhparent IN ('th.trans_rev'::regclass, 'th.trans_head'::regclass) LOOP
                EXECUTE format('ALTER TABLE %s SET (fillfactor=90, autovacuum_vacuum_scale_factor=0.1)', r.child);
              END LOOP;
            END $$;
            """
        )
    else:
        # Fallback for non-PostgreSQL databases (e.g., SQLite)
        status_enum_type = sa.Enum(
            "draft", "reviewed", "published", "rejected", name="translation_status"
        )
        op.create_table(
            "trans_rev",
            sa.Column("project_id", sa.Text(), nullable=False),
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column(
                "content_id",
                sa.Text(),
                sa.ForeignKey("th.content.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("target_lang", sa.Text(), nullable=False),
            sa.Column("variant_key", sa.Text(), nullable=False, server_default="-"),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("status", status_enum_type, nullable=False),
            sa.Column("origin_lang", sa.Text(), nullable=True),
            sa.Column("src_payload_json", json_type, nullable=False),
            sa.Column("translated_payload_json", json_type, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("project_id", "id"),
            sa.UniqueConstraint(
                "project_id",
                "content_id",
                "target_lang",
                "variant_key",
                "revision_no",
                name="uq_rev_dim",
            ),
            schema="th",
        )
        op.create_table(
            "trans_head",
            sa.Column("project_id", sa.Text(), nullable=False),
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column(
                "content_id",
                sa.Text(),
                sa.ForeignKey("th.content.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("target_lang", sa.Text(), nullable=False),
            sa.Column("variant_key", sa.Text(), nullable=False, server_default="-"),
            sa.Column("current_rev_id", sa.Text(), nullable=False),
            sa.Column("current_status", status_enum_type, nullable=False),
            sa.Column("current_no", sa.Integer(), nullable=False),
            sa.Column("published_rev_id", sa.Text(), nullable=True),
            sa.Column("published_no", sa.Integer(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("project_id", "id"),
            sa.UniqueConstraint(
                "project_id",
                "content_id",
                "target_lang",
                "variant_key",
                name="uq_head_dim",
            ),
            sa.UniqueConstraint(
                "project_id", "published_rev_id", name="uq_head_published_rev"
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "current_rev_id"],
                ["th.trans_rev.project_id", "th.trans_rev.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["project_id", "published_rev_id"],
                ["th.trans_rev.project_id", "th.trans_rev.id"],
                ondelete="RESTRICT",
            ),
            schema="th",
        )

    # =====================================================================================
    # 3. 缓存与扩展表
    # =====================================================================================
    op.create_table(
        "resolve_cache",
        sa.Column("project_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("content_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("target_lang", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "variant_key",
            sa.Text(),
            primary_key=True,
            nullable=False,
            server_default="-",
        ),
        sa.Column("resolved_rev_id", sa.Text(), nullable=False),
        sa.Column("resolved_payload", json_type, nullable=False),
        sa.Column("origin_lang", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["th.projects.project_id"],
            name=op.f("fk_resolve_cache_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["th.content.id"],
            name=op.f("fk_resolve_cache_content_id_content"),
            ondelete="CASCADE",
        ),
        *_compact_args(
            sa.CheckConstraint(
                "th.is_bcp47(target_lang)", name="ck_cache_target_lang_bcp47"
            )
            if dialect == "postgresql"
            else None,
            sa.CheckConstraint(
                "origin_lang IS NULL OR th.is_bcp47(origin_lang)",
                name="ck_cache_origin_lang_bcp47",
            )
            if dialect == "postgresql"
            else None,
        ),
        schema="th",
    )
    if dialect == "postgresql":
        op.create_foreign_key(
            "fk_resolve_cache_rev",
            "resolve_cache",
            "trans_rev",
            ["project_id", "resolved_rev_id"],
            ["project_id", "id"],
            source_schema="th",
            referent_schema="th",
            ondelete="CASCADE",
        )
    op.create_index(
        "ix_resolve_expires", "resolve_cache", ["expires_at"], unique=False, schema="th"
    )

    op.create_table(
        "events",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True
        ),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column(
            "actor", sa.Text(), nullable=False, server_default=sa.text("'system'")
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            ondelete="CASCADE",
        ),
        schema="th",
    )
    op.create_index("ix_events_head", "events", ["project_id", "head_id"], schema="th")

    op.create_table(
        "comments",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True
        ),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("head_id", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "head_id"],
            ["th.trans_head.project_id", "th.trans_head.id"],
            ondelete="CASCADE",
        ),
        schema="th",
    )
    op.create_index(
        "ix_comments_head", "comments", ["project_id", "head_id"], schema="th"
    )

    op.create_table(
        "tm_units",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("th.projects.project_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("src_lang", sa.Text(), nullable=False),
        sa.Column("tgt_lang", sa.Text(), nullable=False),
        sa.Column("src_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("src_payload", json_type, nullable=False),
        sa.Column("tgt_payload", json_type, nullable=False),
        sa.Column("variant_key", sa.Text(), nullable=False, server_default="-"),
        sa.Column(
            "approved", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "project_id",
            "namespace",
            "src_hash",
            "tgt_lang",
            "variant_key",
            name="uq_tm_units_dim",
        ),
        *_compact_args(
            sa.CheckConstraint("th.is_bcp47(src_lang)", name="ck_tm_src_lang_bcp47")
            if dialect == "postgresql"
            else None,
            sa.CheckConstraint("th.is_bcp47(tgt_lang)", name="ck_tm_tgt_lang_bcp47")
            if dialect == "postgresql"
            else None,
        ),
        schema="th",
    )

    op.create_table(
        "tm_links",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("translation_rev_id", sa.Text(), nullable=False),
        sa.Column(
            "tm_id",
            sa.Text(),
            sa.ForeignKey("th.tm_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "translation_rev_id"],
            ["th.trans_rev.project_id", "th.trans_rev.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"
        ),
        schema="th",
    )
    op.create_index(
        op.f("ix_tm_links_tm_id"),
        "tm_links",
        ["project_id", "tm_id"],
        unique=False,
        schema="th",
    )

    op.create_table(
        "locales_fallbacks",
        sa.Column(
            "project_id",
            sa.Text(),
            sa.ForeignKey("th.projects.project_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("locale", sa.Text(), primary_key=True),
        sa.Column("fallback_order", json_type, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *_compact_args(
            sa.CheckConstraint("th.is_bcp47(locale)", name="ck_locales_fallbacks_bcp47")
            if dialect == "postgresql"
            else None,
        ),
        schema="th",
    )

    # =====================================================================================
    # 4. 搜索物化视图与索引
    # =====================================================================================
    if dialect == "postgresql":
        op.execute(
            """
            CREATE MATERIALIZED VIEW th.search_rev AS
            SELECT r.project_id, r.content_id, r.target_lang, r.variant_key, r.id AS rev_id, to_tsvector('simple', th.extract_text(r.translated_payload_json)) AS tsv, r.updated_at
            FROM th.trans_rev r
            WHERE r.status IN ('reviewed','published');

            CREATE UNIQUE INDEX ux_search_rev_ident ON th.search_rev (project_id, content_id, target_lang, variant_key, rev_id);
            CREATE INDEX ix_search_rev_tsv ON th.search_rev USING GIN (tsv);
            CREATE INDEX ix_trans_rev_trgm ON th.trans_rev USING GIN ((translated_payload_json::text) gin_trgm_ops);
            """
        )

    # =====================================================================================
    # 5. 函数与触发器 (仅限 PostgreSQL)
    # =====================================================================================
    if dialect == "postgresql":
        op.execute(
            """
            DO $$ DECLARE t_name TEXT; BEGIN
              FOR t_name IN SELECT table_name FROM information_schema.tables WHERE table_schema='th' AND table_name IN ('content', 'trans_rev', 'trans_head', 'resolve_cache', 'tm_units', 'locales_fallbacks') LOOP
                EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_updated_at BEFORE INSERT OR UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();', t_name);
              END LOOP;
              FOR t_name IN SELECT table_name FROM information_schema.tables WHERE table_schema='th' AND table_name IN ('trans_rev', 'trans_head', 'resolve_cache') LOOP
                 EXECUTE format('CREATE OR REPLACE TRIGGER trg_%1$s_variant_norm BEFORE INSERT OR UPDATE ON th.%1$s FOR EACH ROW EXECUTE FUNCTION th.variant_normalize();', t_name);
              END LOOP;
              -- [新增] 应用 UIDA 不可变性触发器
              EXECUTE 'CREATE OR REPLACE TRIGGER trg_forbid_content_uida_update BEFORE UPDATE ON th.content FOR EACH ROW EXECUTE FUNCTION th.forbid_uida_update();';
            END; $$;
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.emit_event(p_project_id TEXT, p_head_id TEXT, p_event TEXT, p_payload JSONB DEFAULT '{}'::jsonb, p_actor TEXT DEFAULT 'system') RETURNS VOID LANGUAGE sql AS $$
            INSERT INTO th.events(project_id, head_id, event_type, payload, actor) VALUES (p_project_id, p_head_id, p_event, coalesce(p_payload,'{}'::jsonb), p_actor);
            $$;

            CREATE OR REPLACE FUNCTION th.invalidate_resolve_cache_for_head(p_project_id TEXT, p_content_id TEXT, p_target_lang TEXT, p_variant_key TEXT) RETURNS INTEGER LANGUAGE plpgsql AS $$
            DECLARE v_count INTEGER; BEGIN DELETE FROM th.resolve_cache WHERE project_id = p_project_id AND content_id = p_content_id AND target_lang = p_target_lang AND variant_key = p_variant_key; GET DIAGNOSTICS v_count = ROW_COUNT; RETURN v_count; END;
            $$;

            CREATE OR REPLACE FUNCTION th.on_head_publish_unpublish() RETURNS TRIGGER LANGUAGE plpgsql AS $$
            DECLARE v_event TEXT; v_deleted INTEGER; BEGIN
              IF TG_OP = 'UPDATE' AND OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id THEN
                v_event := CASE WHEN NEW.published_rev_id IS NULL THEN 'unpublished' ELSE 'published' END;
                PERFORM th.emit_event(NEW.project_id, NEW.id, v_event, jsonb_build_object('old_rev', OLD.published_rev_id, 'new_rev', NEW.published_rev_id, 'content_id', NEW.content_id));
                v_deleted := th.invalidate_resolve_cache_for_head(NEW.project_id, NEW.content_id, NEW.target_lang, NEW.variant_key);
                PERFORM pg_notify('th_search_mv_refresh', json_build_object('event', v_event, 'content_id', NEW.content_id, 'deleted_cache', v_deleted)::text);
              END IF;
              RETURN NEW;
            END; $$;

            CREATE OR REPLACE TRIGGER trg_head_publish_unpublish
              AFTER UPDATE OF published_rev_id ON th.trans_head
              FOR EACH ROW WHEN (OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id)
              EXECUTE FUNCTION th.on_head_publish_unpublish();
            """
        )

    # =====================================================================================
    # 6. 行级安全 (RLS, 仅 PostgreSQL)
    # =====================================================================================
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
            DECLARE v TEXT := current_setting('th.allowed_projects', true); BEGIN IF v IS NULL OR v = '' THEN RETURN ARRAY[]::TEXT[]; END IF; RETURN string_to_array(regexp_replace(v, '\\s+', '', 'g'), ','); END;
            $$;
            """
        )
        op.execute(
            """
            DO $$ DECLARE t_name TEXT; BEGIN
              FOR t_name IN SELECT tablename FROM pg_tables WHERE schemaname = 'th' AND tablename <> 'search_rev' LOOP
                EXECUTE format('ALTER TABLE th.%I ENABLE ROW LEVEL SECURITY;', t_name);
                EXECUTE format(
                  'CREATE POLICY p_%1$s_rls ON th.%1$s FOR ALL TO PUBLIC USING (cardinality(th.allowed_projects()) = 0 OR project_id = ANY(th.allowed_projects())) WITH CHECK (cardinality(th.allowed_projects()) = 0 OR project_id = ANY(th.allowed_projects()));',
                  t_name
                );
              END LOOP;
            END; $$;
            """
        )

    # =====================================================================================
    # 7. 兼容性视图
    # =====================================================================================
    if dialect == "postgresql":
        op.execute(
            """
            DO $$ BEGIN
                CREATE OR REPLACE VIEW public.th_projects      AS SELECT * FROM th.projects;
                CREATE OR REPLACE VIEW public.th_content       AS SELECT * FROM th.content;
                CREATE OR REPLACE VIEW public.th_trans_rev     AS SELECT * FROM th.trans_rev;
                CREATE OR REPLACE VIEW public.th_trans_head    AS SELECT * FROM th.trans_head;
                CREATE OR REPLACE VIEW public.th_resolve_cache AS SELECT * FROM th.resolve_cache;
                CREATE OR REPLACE VIEW public.th_events        AS SELECT * FROM th.events;
                CREATE OR REPLACE VIEW public.th_comments      AS SELECT * FROM th.comments;
                CREATE OR REPLACE VIEW public.th_tm_units      AS SELECT * FROM th.tm_units;
                CREATE OR REPLACE VIEW public.th_tm_links      AS SELECT * FROM th.tm_links;
                CREATE OR REPLACE VIEW public.th_locales_fallbacks AS SELECT * FROM th.locales_fallbacks;
            END; $$;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        # A more robust downgrade that removes all objects created by this migration
        op.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        op.execute(
            "GRANT ALL ON SCHEMA public TO postgres; GRANT ALL ON SCHEMA public TO public;"
        )
        op.execute("DROP SCHEMA IF EXISTS th CASCADE;")
        op.execute("DROP TYPE IF EXISTS th.translation_status CASCADE;") # Drop type which might linger
    else:
        # For SQLite, drop tables in reverse order of creation
        tables_to_drop = [
            "locales_fallbacks",
            "tm_links",
            "tm_units",
            "comments",
            "events",
            "resolve_cache",
            "trans_head",
            "trans_rev",
            "content",
            "projects",
        ]
        for table in tables_to_drop:
            op.drop_table(table, schema="th")
