# alembic/versions/3f8b9e6a0c2c_initial_schema.py
# [v2.4.1 - Initial Schema · Composite PK for Partitioned Tables · Shadow Index (Minimal)]
"""
TRANS-HUB 数据库初始化（v2.4.1 · UIDA + Rev/Head + 影子索引最小占位 + Resolve Cache）

特性与约束（本版关键点）：
- UIDA：th_content 上以 (project_id, namespace, keys_sha256_bytes) 唯一且不可更新。
- 译文历史/头表：th_trans_rev / th_trans_head 采用 HASH(project_id) 分区；
  **主键均为 (project_id, id)**（满足 PG 对“分区表唯一约束必须包含分区键”的硬性规则）。
- 影子索引表 search_content：仅包含 content_id（PK+FK），不预填充任何业务列；
  PostgreSQL 提供最小触发器，仅维护占位行存在/删除。后续按项目通过新迁移追加列与索引。
- SQLite 插件：不创建 plpgsql 函数/触发器；保持同名表与最小契约（字段对齐，能力降级）。

兼容数据库：
- PostgreSQL（推荐 ≥ 14）
- SQLite（插件/离线最小子集）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# --- Alembic 元数据 ---
revision = "3f8b9e6a0c2c"
down_revision = None
branch_labels = None
depends_on = None


def _json_type(dialect_name: str) -> sa.types.TypeEngine:
    """
    按方言选择 JSON 类型：
    - PostgreSQL 使用 JSONB（结合 ->、->>、@> 等操作更高效）
    - 其它方言（SQLite）使用通用 JSON（依赖 json1 扩展）
    """
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    JSONType = _json_type(dialect)

    # ----------------------------------------------------------------------
    # 0) 定义枚举：译文状态（仅 4 态）
    #    PG：先确保枚举类型存在；其它方言：直接用 SQLAlchemy Enum（退化为 CHECK）
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
        sa.Column("project_id", sa.String(), nullable=False, comment="项目主键（短而稳；命名规则详见白皮书）"),
        sa.Column("display_name", sa.String(), nullable=False, comment="项目自然名，便于人读"),
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
    # 2) th_content：源内容权威（UIDA 三元唯一且不可更新）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_content",
        sa.Column("id", sa.String(), nullable=False, comment="PK（无业务含义，字符串 UUID/雪花 ID）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="FK → th_projects.project_id"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容域 + 语义主版本（如 game.ui.menu.entry.v1）"),
        sa.Column("keys_sha256_bytes", sa.LargeBinary(length=32), nullable=False, comment="JCS(keys_json)→SHA-256 32B 摘要"),
        sa.Column("keys_b64", sa.Text(), nullable=False, comment="JCS(keys_json) 的 Base64URL 文本（排错/导出用）"),
        sa.Column("keys_json", JSONType, nullable=False, comment="权威 keys（I-JSON；参与 UIDA 计算）"),
        sa.Column("source_payload_json", JSONType, nullable=False, comment="结构化原文与元数据（不含译文）"),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="业务侧内容版本"),
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
    # 3) th_trans_rev（历史 · 分区：HASH(project_id)）  —— 主键改为 (project_id, id)
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        # 父表（分区表）
        op.execute(
            """
            CREATE TABLE th_trans_rev (
              project_id              TEXT NOT NULL REFERENCES th_projects(project_id),
              id                      TEXT NOT NULL,
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
              created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (project_id, id)
            ) PARTITION BY HASH (project_id);
            """
        )

        # 分区与索引（8 片；如需可调整）
        op.execute(
            """
            DO $$
            DECLARE i int;
            BEGIN
              FOR i IN 0..7 LOOP
                EXECUTE format(
                  'CREATE TABLE IF NOT EXISTS th_trans_rev_p%s PARTITION OF th_trans_rev FOR VALUES WITH (MODULUS 8, REMAINDER %s);',
                  i, i
                );
                EXECUTE format(
                  'CREATE INDEX IF NOT EXISTS ix_rev_p%s_content_lang ON th_trans_rev_p%s(content_id, target_lang);',
                  i, i
                );
              END LOOP;
            END $$;
            """
        )

        # 由 content_id 派生 project_id（插入时自动赋值）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_trans_derive_project_rev()
            RETURNS trigger AS $$
            BEGIN
              -- 若未显式传入，则由 content 派生 project_id
              IF NEW.project_id IS NULL THEN
                SELECT c.project_id INTO NEW.project_id FROM th_content c WHERE c.id = NEW.content_id;
                IF NEW.project_id IS NULL THEN
                  RAISE EXCEPTION 'content_id % not found when deriving project_id (rev)', NEW.content_id;
                END IF;
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            "CREATE TRIGGER trg_rev_derive_project_ins BEFORE INSERT ON th_trans_rev FOR EACH ROW EXECUTE FUNCTION th_trans_derive_project_rev();"
        )
    else:
        # 非 PG：普通表（最小可用子集）
        op.create_table(
            "th_trans_rev",
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
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
            sa.PrimaryKeyConstraint("project_id", "id"),
            sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_rev_content", ondelete="CASCADE"),
        )
        op.create_index("ix_rev_content_lang", "th_trans_rev", ["content_id", "target_lang"], unique=False)

    # ----------------------------------------------------------------------
    # 4) th_trans_head（头表 · 分区：HASH(project_id)） —— 主键改为 (project_id, id)
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute(
            """
            CREATE TABLE th_trans_head (
              project_id        TEXT NOT NULL REFERENCES th_projects(project_id),
              id                TEXT NOT NULL,
              content_id        TEXT NOT NULL REFERENCES th_content(id) ON DELETE CASCADE,
              target_lang       TEXT NOT NULL,
              variant_key       TEXT NOT NULL DEFAULT '-',
              current_rev_id    TEXT NOT NULL,
              current_status    translation_status NOT NULL,
              current_no        INTEGER NOT NULL,
              published_rev_id  TEXT,
              published_no      INTEGER,
              published_at      TIMESTAMPTZ,
              updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (project_id, id),

              -- 维度唯一（同 content/lang/variant 仅一行头表）
              CONSTRAINT uq_head_dim UNIQUE (project_id, content_id, target_lang, variant_key),

              -- 关联当前与已发布修订（复合外键，包含分区键）
              FOREIGN KEY (project_id, current_rev_id)
                REFERENCES th_trans_rev(project_id, id) ON DELETE CASCADE,
              FOREIGN KEY (project_id, published_rev_id)
                REFERENCES th_trans_rev(project_id, id),

              -- 项目内发布指针唯一（允许 NULL）
              CONSTRAINT uq_head_published_rev UNIQUE (project_id, published_rev_id)
            ) PARTITION BY HASH (project_id);
            """
        )

        op.execute(
            """
            DO $$
            DECLARE i int;
            BEGIN
              FOR i IN 0..7 LOOP
                EXECUTE format(
                  'CREATE TABLE IF NOT EXISTS th_trans_head_p%s PARTITION OF th_trans_head FOR VALUES WITH (MODULUS 8, REMAINDER %s);',
                  i, i
                );
                EXECUTE format(
                  'CREATE INDEX IF NOT EXISTS ix_head_p%s_proj_lang_status_id ON th_trans_head_p%s(project_id, target_lang, current_status, id);',
                  i, i
                );
              END LOOP;
            END $$;
            """
        )

        # 由 content_id 派生 project_id（插入时自动赋值）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_trans_derive_project_head()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.project_id IS NULL THEN
                SELECT c.project_id INTO NEW.project_id FROM th_content c WHERE c.id = NEW.content_id;
                IF NEW.project_id IS NULL THEN
                  RAISE EXCEPTION 'content_id % not found when deriving project_id (head)', NEW.content_id;
                END IF;
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
        op.create_table(
            "th_trans_head",
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
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
            sa.PrimaryKeyConstraint("project_id", "id"),
            sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_head_content", ondelete="CASCADE"),
            sa.UniqueConstraint("project_id", "content_id", "target_lang", "variant_key", name="uq_head_dim"),
            sa.UniqueConstraint("project_id", "published_rev_id", name="uq_head_published_rev"),
        )
        op.create_index("ix_head_proj_lang_status_id", "th_trans_head", ["project_id", "target_lang", "current_status", "id"], unique=False)

    # ----------------------------------------------------------------------
    # 5) search_content：影子索引表（**最小占位**，仅 content_id；不预填充）
    # ----------------------------------------------------------------------
    op.create_table(
        "search_content",
        sa.Column("content_id", sa.String(), nullable=False, comment="PK + FK → th_content.id（仅占位）"),
        sa.PrimaryKeyConstraint("content_id"),
        sa.ForeignKeyConstraint(["content_id"], ["th_content.id"], name="fk_sc_content", ondelete="CASCADE"),
    )

    if dialect == "postgresql":
        # 最小触发器：仅维持占位行（INSERT/UPDATE：确保存在；DELETE：同步删除）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION trg_sc_minimal_touch()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                DELETE FROM search_content WHERE content_id = OLD.id;
                RETURN OLD;
              END IF;

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
    # 6) th_tm（翻译记忆） 与 th_tm_links（追溯）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_tm",
        sa.Column("id", sa.String(), nullable=False, comment="PK（无业务含义）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="项目/租户"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容域"),
        sa.Column("reuse_sha256_bytes", sa.LargeBinary(length=32), nullable=False, comment="复用键摘要（32B）"),
        sa.Column("source_text_json", JSONType, nullable=False, comment="归一化后的源文本骨架/占位符"),
        sa.Column("translated_json", JSONType, nullable=False, comment="结构化可复用译文"),
        sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'"), comment="语言内变体"),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("visibility_scope", sa.String(), nullable=False, server_default=sa.text("'project'"), comment="project|tenant|global"),
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

    # th_tm_links：外键指向复合主键 (project_id, id) 的 th_trans_rev
    op.create_table(
        "th_tm_links",
        sa.Column("id", sa.String(), nullable=False, comment="PK（无业务含义）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="镜像项目（与 rev 一致，用于复合外键）"),
        sa.Column("translation_rev_id", sa.String(), nullable=False, comment="指向 th_trans_rev.id（配合 project_id）"),
        sa.Column("tm_id", sa.String(), nullable=False, comment="指向 th_tm.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tm_id"], ["th_tm.id"], name="fk_tm_links_tm", ondelete="CASCADE"),
        # 复合外键：确保链接到同一 project 的 rev 行
        sa.ForeignKeyConstraint(["project_id", "translation_rev_id"], ["th_trans_rev.project_id", "th_trans_rev.id"], name="fk_tm_links_rev", ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"),
    )

    if dialect == "postgresql":
        op.execute(
            "CREATE TRIGGER trg_tm_touch_updated_at BEFORE UPDATE ON th_tm FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )

    # ----------------------------------------------------------------------
    # 7) 语言回退策略 与 解析缓存
    # ----------------------------------------------------------------------
    op.create_table(
        "th_locales_fallbacks",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column("fallback_order", JSONType, nullable=False, comment="回退顺序数组，如 ['zh-Hans','zh']"),
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
        sa.Column("resolved_rev", sa.String(), nullable=False, comment="命中的修订 id（与 project_id 配对使用）"),
        sa.Column("origin_lang", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("content_id", "target_lang", "variant_key"),
    )
    op.create_index("ix_resolve_project", "th_resolve_cache", ["project_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ----------------------------------------------------------------------
    # 7) 回退策略与解析缓存
    # ----------------------------------------------------------------------
    op.drop_index("ix_resolve_project", table_name="th_resolve_cache")
    op.drop_table("th_resolve_cache")
    op.drop_table("th_locales_fallbacks")

    # ----------------------------------------------------------------------
    # 6) TM 与链接
    # ----------------------------------------------------------------------
    op.drop_table("th_tm_links")
    op.drop_index("ix_tm_last_used", table_name="th_tm")
    op.drop_table("th_tm")

    # ----------------------------------------------------------------------
    # 5) 影子索引表（及触发器/函数）
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_sc_ins ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_upd ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_del ON th_content;")
        op.execute("DROP FUNCTION IF EXISTS trg_sc_minimal_touch();")
    op.drop_table("search_content")

    # ----------------------------------------------------------------------
    # 4) 头表（与分区对象）
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_head_touch_updated_at ON th_trans_head;")
        op.execute("DROP TRIGGER IF EXISTS trg_head_derive_project_ins ON th_trans_head;")
        op.execute("DROP TABLE IF EXISTS th_trans_head CASCADE;")
    else:
        op.drop_index("ix_head_proj_lang_status_id", table_name="th_trans_head")
        op.drop_table("th_trans_head")

    # ----------------------------------------------------------------------
    # 3) 历史表（与分区对象）
    # ----------------------------------------------------------------------
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_rev_derive_project_ins ON th_trans_rev;")
        op.execute("DROP TABLE IF EXISTS th_trans_rev CASCADE;")
        # 最后再清理枚举类型（避免残留）
        op.execute("DROP TYPE IF EXISTS translation_status;")
    else:
        op.drop_index("ix_rev_content_lang", table_name="th_trans_rev")
        op.drop_table("th_trans_rev")

    # ----------------------------------------------------------------------
    # 2) 内容表
    # ----------------------------------------------------------------------
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

    # ----------------------------------------------------------------------
    # 1) 项目注册
    # ----------------------------------------------------------------------
    op.drop_table("th_projects")