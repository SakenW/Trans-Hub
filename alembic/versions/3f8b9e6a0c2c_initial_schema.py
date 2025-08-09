# alembic/versions/3f8b9e6a0c2c_initial_schema.py
# [v2.4 - Initial Schema · Shadow Index Table Without Business Columns]
"""
TRANS-HUB 数据库初始化（v2.4 · UIDA + Rev/Head + Minimal Shadow + Resolve Cache）

特性与约束：
- 影子索引表 search_content 仅包含 content_id（PK+FK），**不含任何业务列**，不预填充。
- PostgreSQL：提供最小触发器（仅保持占位行存在/删除），后续你可通过新迁移追加列与索引。
- SQLite 插件：不创建 plpgsql 函数/触发器；影子表保持同名同契约（仅 content_id），后续列按需迁移追加。

兼容数据库：
- PostgreSQL（推荐 ≥ 14）
- SQLite（插件/离线最小子集）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# --- Alembic metadata ---
revision = "3f8b9e6a0c2c"
down_revision = None
branch_labels = None
depends_on = None


def _json_type(dialect_name: str) -> sa.types.TypeEngine:
    """PG 用 JSONB，其它方言用通用 JSON。"""
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    JSONType = _json_type(dialect)

    # ----------------------------------------------------------------------
    # 0) ENUM：译文状态
    #   - PG：在使用前显式创建枚举类型
    #   - 其它方言：用 SQLAlchemy Enum（会退化为 CHECK）
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'translation_status') THEN
                CREATE TYPE translation_status AS ENUM ('draft','reviewed','published','rejected');
              END IF;
            END $$;
            """
        )
    translation_status = sa.Enum("draft", "reviewed", "published", "rejected", name="translation_status")

    # ----------------------------------------------------------------------
    # 1) th_projects：项目集中注册（强校验 + 不可改名）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_projects",
        sa.Column("project_id", sa.String(), nullable=False, comment="项目主键（短而稳）"),
        sa.Column("display_name", sa.String(), nullable=False, comment="自然名（便于人读）"),
        sa.Column("category", sa.String(), nullable=True, comment="元数据：mod/pack/app/web/site 等"),
        sa.Column("platform", sa.String(), nullable=True, comment="元数据：minecraft/ios/android/web 等"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("project_id"),
        sa.CheckConstraint("char_length(project_id) BETWEEN 3 AND 32", name="ck_proj_len"),
        sa.CheckConstraint("project_id NOT LIKE '-%'", name="ck_proj_no_prefix_dash"),
        sa.CheckConstraint("project_id NOT LIKE '%-'", name="ck_proj_no_suffix_dash"),
        sa.CheckConstraint("project_id NOT LIKE '%--%'", name="ck_proj_no_double_dash"),
        sa.CheckConstraint(
            "project_id NOT IN ('default','root','admin','system','sys','internal','tmp','test','staging','prod','production','null','true','false','public')",
            name="ck_proj_reserved",
        ),
    )

    if dialect == "postgresql":
        # 通用更新时间触发器函数
        op.execute(
            """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS trigger AS $$
            BEGIN
              NEW.updated_at = CURRENT_TIMESTAMP;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        # 不可改名触发器
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_projects_forbid_rename()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
                RAISE EXCEPTION 'project_id is immutable';
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            "CREATE TRIGGER trg_projects_forbid_rename BEFORE UPDATE ON th_projects FOR EACH ROW EXECUTE FUNCTION th_projects_forbid_rename();"
        )
        op.execute(
            "CREATE TRIGGER trg_projects_touch_updated_at BEFORE UPDATE ON th_projects FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )

    # ----------------------------------------------------------------------
    # 2) th_content：源内容（含 keys_json），UIDA 不变
    # ----------------------------------------------------------------------
    op.create_table(
        "th_content",
        sa.Column("id", sa.String(), nullable=False, comment="PK（无业务含义）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="FK → th_projects.project_id"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容域 + 语义主版本"),
        sa.Column("keys_sha256_bytes", sa.LargeBinary(length=32), nullable=False, comment="JCS(keys_json)→SHA256 32B"),
        sa.Column("keys_b64", sa.Text(), nullable=False, comment="JCS(keys_json) 的 Base64URL 文本"),
        sa.Column("keys_json", JSONType, nullable=False, comment="权威 keys（I-JSON；参与 UIDA）"),
        sa.Column("source_payload_json", JSONType, nullable=False, comment="结构化原文与元数据（不含译文）"),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="业务内容版本"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True, comment="归档时间（可选）"),
        sa.Column("content_type", sa.String(), nullable=True, comment="内容类型（可选）"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["th_projects.project_id"], name="fk_content_project"),
        sa.UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),
        sa.CheckConstraint(
            "(octet_length(keys_sha256_bytes)=32) OR (length(keys_sha256_bytes)=32)", name="ck_content_keys_sha256_len"
        ),
    )
    op.create_index("ix_content_proj_ns", "th_content", ["project_id", "namespace"], unique=False)
    op.create_index("ix_content_proj_ns_ver", "th_content", ["project_id", "namespace", "content_version"], unique=False)

    if dialect == "postgresql":
        # UIDA 三元不可更新
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_content_forbid_uida_update()
            RETURNS trigger AS $$
            BEGIN
              IF (OLD.project_id IS DISTINCT FROM NEW.project_id)
                 OR (OLD.namespace IS DISTINCT FROM NEW.namespace)
                 OR (OLD.keys_sha256_bytes IS DISTINCT FROM NEW.keys_sha256_bytes) THEN
                RAISE EXCEPTION 'UIDA fields are immutable';
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            "CREATE TRIGGER trg_content_forbid_uida_update BEFORE UPDATE ON th_content FOR EACH ROW EXECUTE FUNCTION th_content_forbid_uida_update();"
        )
        op.execute(
            "CREATE TRIGGER trg_content_touch_updated_at BEFORE UPDATE ON th_content FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )

    # ----------------------------------------------------------------------
    # 3) th_trans_rev（历史 · PG 分区） + 4) th_trans_head（头表 · PG 分区）
    #    非 PG：退化为普通表（最小可用）
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        # 历史表（父表）
        op.execute(
            """
            CREATE TABLE th_trans_rev (
              id                      TEXT PRIMARY KEY,
              project_id              TEXT NOT NULL REFERENCES th_projects(project_id),
              content_id              TEXT NOT NULL REFERENCES th_content(id) ON DELETE CASCADE,
              target_lang             TEXT NOT NULL,
              variant_key             TEXT NOT NULL DEFAULT '-',
              status                  translation_status NOT NULL,
              revision_no             INTEGER NOT NULL,
              translated_payload_json JSONB,
              origin_lang             TEXT,
              quality_score           DOUBLE PRECISION,
              lint_report_json        JSONB,
              engine_name             TEXT,
              engine_version          TEXT,
              prompt_hash             TEXT,
              params_hash             TEXT,
              created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) PARTITION BY HASH (project_id);
            """
        )
        # 头表（父表）
        op.execute(
            """
            CREATE TABLE th_trans_head (
              id               TEXT PRIMARY KEY,
              project_id       TEXT NOT NULL REFERENCES th_projects(project_id),
              content_id       TEXT NOT NULL REFERENCES th_content(id) ON DELETE CASCADE,
              target_lang      TEXT NOT NULL,
              variant_key      TEXT NOT NULL DEFAULT '-',
              current_rev_id   TEXT NOT NULL REFERENCES th_trans_rev(id) ON DELETE CASCADE,
              current_status   translation_status NOT NULL,
              current_no       INTEGER NOT NULL,
              published_rev_id TEXT,
              published_no     INTEGER,
              published_at     TIMESTAMPTZ,
              updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
              CONSTRAINT uq_head_dim UNIQUE (project_id, content_id, target_lang, variant_key),
              CONSTRAINT uq_head_published_rev UNIQUE (project_id, published_rev_id)
            ) PARTITION BY HASH (project_id);
            """
        )
        # 建 8 片 HASH 分区与常用索引
        op.execute(
            """
            DO $$
            DECLARE i int;
            BEGIN
              FOR i IN 0..7 LOOP
                EXECUTE format('CREATE TABLE IF NOT EXISTS th_trans_rev_p%s PARTITION OF th_trans_rev FOR VALUES WITH (MODULUS 8, REMAINDER %s);', i, i);
                EXECUTE format('CREATE INDEX IF NOT EXISTS ix_rev_p%s_content_lang ON th_trans_rev_p%s(content_id, target_lang);', i, i);
                EXECUTE format('CREATE TABLE IF NOT EXISTS th_trans_head_p%s PARTITION OF th_trans_head FOR VALUES WITH (MODULUS 8, REMAINDER %s);', i, i);
                EXECUTE format('CREATE INDEX IF NOT EXISTS ix_head_p%s_proj_lang_status_id ON th_trans_head_p%s(project_id, target_lang, current_status, id);', i, i);
              END LOOP;
            END $$;
            """
        )
        # 自动派生 project_id（从 content_id）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_trans_derive_project_rev()
            RETURNS trigger AS $$
            BEGIN
              SELECT c.project_id INTO NEW.project_id FROM th_content c WHERE c.id = NEW.content_id;
              IF NEW.project_id IS NULL THEN
                RAISE EXCEPTION 'content_id % not found when deriving project_id (rev)', NEW.content_id;
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            "CREATE TRIGGER trg_rev_derive_project_ins BEFORE INSERT ON th_trans_rev FOR EACH ROW EXECUTE FUNCTION th_trans_derive_project_rev();"
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_trans_derive_project_head()
            RETURNS trigger AS $$
            BEGIN
              SELECT c.project_id INTO NEW.project_id FROM th_content c WHERE c.id = NEW.content_id;
              IF NEW.project_id IS NULL THEN
                RAISE EXCEPTION 'content_id % not found when deriving project_id (head)', NEW.content_id;
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            "CREATE TRIGGER trg_head_derive_project_ins BEFORE INSERT ON th_trans_head FOR EACH ROW EXECUTE FUNCTION th_trans_derive_project_head();"
        )
        op.execute(
            "CREATE TRIGGER trg_head_touch_updated_at BEFORE UPDATE ON th_trans_head FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        # --- 非 PG：退化为普通表（最小可用子集） ---
        op.create_table(
            "th_trans_rev",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), nullable=False),
            sa.Column("target_lang", sa.String(), nullable=False),
            sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
            sa.Column("status", translation_status, nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("translated_payload_json", JSONType, nullable=True),
            sa.Column("origin_lang", sa.String(), nullable=True),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("lint_report_json", JSONType, nullable=True),
            sa.Column("engine_name", sa.String(), nullable=True),
            sa.Column("engine_version", sa.String(), nullable=True),
            sa.Column("prompt_hash", sa.String(), nullable=True),
            sa.Column("params_hash", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_rev_content", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_rev_content_lang", "th_trans_rev", ["content_id", "target_lang"], unique=False)

        op.create_table(
            "th_trans_head",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), nullable=False),
            sa.Column("target_lang", sa.String(), nullable=False),
            sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
            sa.Column("current_rev_id", sa.String(), nullable=False),
            sa.Column("current_status", translation_status, nullable=False),
            sa.Column("current_no", sa.Integer(), nullable=False),
            sa.Column("published_rev_id", sa.String(), nullable=True),
            sa.Column("published_no", sa.Integer(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_head_content", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"),
            sa.UniqueConstraint("project_id", "published_rev_id", name="uq_head_published_rev"),
        )
        op.create_index("ix_head_proj_lang_status_id", "th_trans_head", ["project_id", "target_lang", "current_status", "id"], unique=False)

    # ----------------------------------------------------------------------
    # 5) search_content：影子索引表（**不带业务列**；仅 content_id）
    #    - 目的：占位与外键；后续按项目生成迁移追加列与索引
    #    - 本迁移不回填、不解析、不建立业务索引
    # ----------------------------------------------------------------------
    op.create_table(
        "search_content",
        sa.Column("content_id", sa.String(), nullable=False, comment="PK + FK → th_content.id"),
        sa.PrimaryKeyConstraint("content_id"),
        sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_sc_content", ondelete="CASCADE"),
    )

    if dialect == "postgresql":
        # 最小触发器：仅维持占位行（INSERT/UPDATE：确保存在；DELETE：删除）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION trg_sc_minimal_touch()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                DELETE FROM search_content WHERE content_id = OLD.id;
                RETURN OLD;
              END IF;

              -- INSERT / UPDATE：只确保存在占位行，不写任何业务列
              INSERT INTO search_content(content_id)
              VALUES (NEW.id)
              ON CONFLICT (content_id) DO NOTHING;

              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("CREATE TRIGGER trg_sc_ins AFTER INSERT ON th_content FOR EACH ROW EXECUTE FUNCTION trg_sc_minimal_touch();")
        op.execute("CREATE TRIGGER trg_sc_upd AFTER UPDATE OF keys_json, namespace, project_id ON th_content FOR EACH ROW EXECUTE FUNCTION trg_sc_minimal_touch();")
        op.execute("CREATE TRIGGER trg_sc_del AFTER DELETE ON th_content FOR EACH ROW EXECUTE FUNCTION trg_sc_minimal_touch();")

    # ----------------------------------------------------------------------
    # 6) TM 与链接（与 v2.4 契约一致）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_tm",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("reuse_sha256_bytes", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_text_json", JSONType, nullable=False),
        sa.Column("translated_json", JSONType, nullable=False),
        sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("visibility_scope", sa.String(), nullable=False, server_default=sa.text("'project'")),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("hash_algo_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("reuse_policy_fingerprint", sa.String(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("pii_flags", JSONType, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("visibility_scope in ('project','tenant','global')", name="ck_tm_visibility_scope"),
        sa.CheckConstraint(
            "(octet_length(reuse_sha256_bytes)=32) OR (length(reuse_sha256_bytes)=32)", name="ck_tm_reuse_sha256_len"
        ),
        sa.UniqueConstraint(
            "project_id", "namespace", "reuse_sha256_bytes", "source_lang",
            "target_lang", "variant_key", "policy_version", "hash_algo_version",
            name="uq_tm_reuse_key",
        ),
    )
    op.create_index("ix_tm_last_used", "th_tm", ["last_used_at"], unique=False)

    op.create_table(
        "th_tm_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("translation_rev_id", sa.String(), nullable=False),
        sa.Column("tm_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["translation_rev_id"], ["th_trans_rev.id"], name="fk_tm_links_rev", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tm_id"], ["th_tm.id"], name="fk_tm_links_tm", ondelete="CASCADE"),
        sa.UniqueConstraint("translation_rev_id", "tm_id", name="uq_tm_links_pair"),
    )

    # ----------------------------------------------------------------------
    # 7) 语言回退策略与解析缓存
    # ----------------------------------------------------------------------
    op.create_table(
        "th_locales_fallbacks",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column("fallback_order", JSONType, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("project_id", "locale"),
        sa.ForeignKeyConstraint(["project_id"], ["th_projects.project_id"], name="fk_fallbacks_project"),
    )

    op.create_table(
        "th_resolve_cache",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("variant_key", sa.String(), nullable=False),
        sa.Column("resolved_rev", sa.String(), nullable=False),
        sa.Column("origin_lang", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("content_id", "target_lang", "variant_key"),
    )
    op.create_index("ix_resolve_project", "th_resolve_cache", ["project_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 7) 回退策略与解析缓存
    op.drop_index("ix_resolve_project", table_name="th_resolve_cache")
    op.drop_table("th_resolve_cache")
    op.drop_table("th_locales_fallbacks")

    # 6) TM 与链接
    op.drop_table("th_tm_links")
    op.drop_index("ix_tm_last_used", table_name="th_tm")
    op.drop_table("th_tm")

    # 5) 影子索引表（及触发器/函数）
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_sc_ins ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_upd ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_del ON th_content;")
        op.execute("DROP FUNCTION IF EXISTS trg_sc_minimal_touch();")
    op.drop_table("search_content")

    # 3/4) Rev/Head
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_head_touch_updated_at ON th_trans_head;")
        op.execute("DROP TRIGGER IF EXISTS trg_head_derive_project_ins ON th_trans_head;")
        op.execute("DROP TRIGGER IF EXISTS trg_rev_derive_project_ins ON th_trans_rev;")
        op.execute("DROP TABLE IF EXISTS th_trans_head CASCADE;")
        op.execute("DROP TABLE IF EXISTS th_trans_rev CASCADE;")
        op.execute("DROP TYPE IF EXISTS translation_status;")
    else:
        op.drop_index("ix_head_proj_lang_status_id", table_name="th_trans_head")
        op.drop_table("th_trans_head")
        op.drop_index("ix_rev_content_lang", table_name="th_trans_rev")
        op.drop_table("th_trans_rev")

    # 2) 内容表
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_content_forbid_uida_update ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_content_touch_updated_at ON th_content;")
        op.execute("DROP FUNCTION IF EXISTS th_content_forbid_uida_update();")
        op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
        op.execute("DROP TRIGGER IF EXISTS trg_projects_forbid_rename ON th_projects;")
        op.execute("DROP TRIGGER IF EXISTS trg_projects_touch_updated_at ON th_projects;")
        op.execute("DROP FUNCTION IF EXISTS th_projects_forbid_rename();")

    op.drop_index("ix_content_proj_ns_ver", table_name="th_content")
    op.drop_index("ix_content_proj_ns", table_name="th_content")
    op.drop_table("th_content")

    # 1) 项目注册
    op.drop_table("th_projects")
