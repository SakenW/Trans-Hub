# TRANS-HUB 初始架构（v2.5.1-r1 · 加固完整版 · SQLite/PG 兼容修订）
"""
本迁移脚本实现白皮书 v2.5.1-r1 的完整数据库结构（PostgreSQL 优先）：
- th schema、公共函数/类型（set_updated_at、is_bcp47、bcp47_normalize 等）
- th_projects（项目注册，含强命名护栏与 RLS）
- th_content（源内容 · UIDA 唯一事实 + 触发器护栏）
- th_trans_rev / th_trans_head（历史修订与头指针，按 project_id HASH 分区，复合主键）
- th_resolve_cache（解析缓存 · TTL 与精准失效）
- 影子索引：search_content（最小占位）+ 注册表/ETL 状态
- TM：th_tm / th_tm_links
- 语言回退：th_locales_fallbacks
- 事件/评论：th_trans_events / th_trans_comments（事件类型白名单 + 索引）
- 术语：别名/使用表 + 四层表达式唯一索引（global/mod/pack/project）
- 变体策略：顺序/白名单/冲突/必填 + 规范化函数与触发器
- 规则包：th_rulesets / th_rules_runs（逻辑唯一）
- RLS：多租访问控制（th.allowed_projects + policy）
- 存储参数：fillfactor/autovacuum 建议（父表与分区子表同步设置）

非 PostgreSQL 方言（如 SQLite）：
- 创建等价表与基础约束/索引；
- 省略分区、表达式索引与 PL/pgSQL 触发器，改由应用层兜底；
- CHECK 约束使用 SQLite 原生函数（length/substr/instr）实现等价逻辑。

运行环境：PostgreSQL >= 14（推荐）
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


# ---------- 工具：根据方言选择 JSON 类型 ----------
def _json_type(dialect_name: str) -> sa.types.TypeEngine:
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    json_type = _json_type(dialect)

    # =====================================================================================
    # 0) PostgreSQL 专有对象（schema / enum / 通用函数 / RLS 辅助函数 / 角色开关）
    # =====================================================================================
    if dialect == "postgresql":
        # schema th
        op.execute("CREATE SCHEMA IF NOT EXISTS th;")

        # translation_status 枚举
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='translation_status') THEN
                CREATE TYPE translation_status AS ENUM ('draft','reviewed','published','rejected');
              END IF;
            END $$;
            """
        )

        # 通用函数：更新时间戳
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.set_updated_at()
            RETURNS trigger AS $$
            BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
            $$ LANGUAGE plpgsql;
            """
        )

        # BCP-47 校验与归一化
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.is_bcp47(tag TEXT) RETURNS BOOLEAN AS $$
            BEGIN
              RETURN tag ~ '^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$';
            END; $$ LANGUAGE plpgsql IMMUTABLE;
            """
        )
        # 兼容 public.is_bcp47（个别应用可能引用）
        op.execute("CREATE OR REPLACE FUNCTION public.is_bcp47(tag TEXT) RETURNS BOOLEAN LANGUAGE sql AS $$ SELECT th.is_bcp47($1) $$;")

        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.bcp47_normalize(tag TEXT)
            RETURNS TEXT AS $$
            DECLARE t TEXT;
            BEGIN
              IF tag IS NULL OR btrim(tag) = '' THEN RETURN tag; END IF;
              t := lower(replace(btrim(tag), '_', '-'));
              RETURN t;
            END; $$ LANGUAGE plpgsql IMMUTABLE;
            """
        )

        # RLS 辅助函数：从会话变量读取允许项目列表
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] AS $$
            DECLARE v TEXT := current_setting('th.allowed_projects', true);
            BEGIN
              IF v IS NULL OR v='' THEN RETURN ARRAY[]::TEXT[]; END IF;
              RETURN string_to_array(v, ',');
            END; $$ LANGUAGE plpgsql STABLE;
            """
        )

        # 角色创建（可选：通过 GUC th.install_roles='on' 时执行）
        op.execute(
            """
            DO $$
            BEGIN
              IF current_setting('th.install_roles', true) = 'on' THEN
                BEGIN CREATE ROLE th_admin     NOINHERIT; EXCEPTION WHEN duplicate_object OR insufficient_privilege THEN NULL; END;
                BEGIN CREATE ROLE th_app_rw    NOINHERIT; EXCEPTION WHEN duplicate_object OR insufficient_privilege THEN NULL; END;
                BEGIN CREATE ROLE th_readonly  NOINHERIT; EXCEPTION WHEN duplicate_object OR insufficient_privilege THEN NULL; END;
                GRANT USAGE ON SCHEMA public, th TO th_app_rw, th_readonly, th_admin;
                GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA th TO th_app_rw, th_admin;
              END IF;
            END $$;
            """
        )

    # =====================================================================================
    # 1) th_projects —— 项目注册（强命名护栏 + RLS）
    # =====================================================================================
    op.create_table(
        "th_projects",
        sa.Column("project_id", sa.String(), primary_key=True, comment="强命名：^[a-z0-9-]{3,32}$"),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("settings_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb") if dialect=="postgresql" else sa.text("'{}'"), comment="项目设置（解析缓存 TTL 等）"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # 命名护栏 —— 按方言分别创建 CHECK 约束
    if dialect == "postgresql":
        op.create_check_constraint("ck_proj_len",              "th_projects", "char_length(project_id) BETWEEN 3 AND 32")
        op.create_check_constraint("ck_proj_no_prefix_dash",   "th_projects", "project_id !~ '^-'" )
        op.create_check_constraint("ck_proj_no_suffix_dash",   "th_projects", "project_id !~ '-$'" )
        op.create_check_constraint("ck_proj_no_double_dash",   "th_projects", "project_id !~ '--'" )
        op.create_check_constraint(
            "ck_proj_reserved",
            "th_projects",
            """
            project_id NOT IN ('default','root','admin','system','sys','internal',
                               'tmp','test','staging','prod','production','null',
                               'true','false','public')
            """,
        )
        # 触发器：禁止修改 project_id；更新 updated_at
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.projects_forbid_rename()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
                RAISE EXCEPTION 'project_id is immutable';
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_projects_forbid_rename ON th_projects;")
        op.execute(
            """
            CREATE TRIGGER trg_projects_forbid_rename
            BEFORE UPDATE ON th_projects
            FOR EACH ROW EXECUTE FUNCTION th.projects_forbid_rename();
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_projects_touch_updated_at ON th_projects;")
        op.execute(
            """
            CREATE TRIGGER trg_projects_touch_updated_at
            BEFORE UPDATE ON th_projects
            FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();
            """
        )
        # RLS（USING + WITH CHECK）
        op.execute("ALTER TABLE th_projects ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_projects_rls ON th_projects;")
        op.execute(
            """
            CREATE POLICY p_projects_rls ON th_projects
            USING (project_id = ANY (th.allowed_projects()))
            WITH CHECK (project_id = ANY (th.allowed_projects()));
            """
        )
    else:
        # SQLite 等价约束
        op.create_check_constraint("ck_proj_len",            "th_projects", "length(project_id) BETWEEN 3 AND 32")
        op.create_check_constraint("ck_proj_no_prefix_dash", "th_projects", "substr(project_id, 1, 1) <> '-'")
        op.create_check_constraint("ck_proj_no_suffix_dash", "th_projects", "substr(project_id, length(project_id), 1) <> '-'")
        op.create_check_constraint("ck_proj_no_double_dash", "th_projects", "instr(project_id, '--') = 0")
        op.create_check_constraint(
            "ck_proj_reserved",
            "th_projects",
            "(project_id NOT IN ('default','root','admin','system','sys','internal',"
            "'tmp','test','staging','prod','production','null','true','false','public'))"
        )

    # =====================================================================================
    # 2) th_content —— 源内容（UIDA 唯一事实 + 触发器护栏）
    # =====================================================================================
    op.create_table(
        "th_content",
        sa.Column("id", sa.String(), primary_key=True, comment="主键（UUID/雪花），无业务含义"),
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("keys_sha256_bytes", sa.LargeBinary(length=32), nullable=False, comment="SHA-256(JCS(keys_json)) 32B"),
        sa.Column("keys_b64", sa.Text(), nullable=False, comment="JCS(keys_json) 的 Base64URL"),
        sa.Column("keys_json", json_type, nullable=False, comment="唯一寻址最小键集（参与 UIDA）"),
        sa.Column("source_payload_json", json_type, nullable=False, comment="原文及元数据（不存译文）"),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),
    )
    op.create_index("ix_content_proj_ns", "th_content", ["project_id", "namespace"], unique=False)
    op.create_index("ix_content_proj_ns_ver", "th_content", ["project_id", "namespace", "content_version"], unique=False)

    if dialect == "postgresql":
        op.create_check_constraint("ck_content_keys_sha256_len", "th_content", "octet_length(keys_sha256_bytes)=32")
        # UIDA 不可变 + updated_at 更新
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.content_forbid_uida_update()
            RETURNS trigger AS $$
            BEGIN
              IF (OLD.project_id IS DISTINCT FROM NEW.project_id)
                 OR (OLD.namespace IS DISTINCT FROM NEW.namespace)
                 OR (OLD.keys_sha256_bytes IS DISTINCT FROM NEW.keys_sha256_bytes) THEN
                RAISE EXCEPTION 'UIDA fields are immutable';
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_content_forbid_uida_update ON th_content;")
        op.execute(
            """
            CREATE TRIGGER trg_content_forbid_uida_update
            BEFORE UPDATE ON th_content
            FOR EACH ROW EXECUTE FUNCTION th.content_forbid_uida_update();
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_content_touch_updated_at ON th_content;")
        op.execute(
            """
            CREATE TRIGGER trg_content_touch_updated_at
            BEFORE UPDATE ON th_content
            FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();
            """
        )
        # RLS（USING + WITH CHECK）
        op.execute("ALTER TABLE th_content ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_content_rls ON th_content;")
        op.execute(
            """
            CREATE POLICY p_content_rls ON th_content
            USING (project_id = ANY (th.allowed_projects()))
            WITH CHECK (project_id = ANY (th.allowed_projects()));
            """
        )

    # =====================================================================================
    # 3) th_trans_rev —— 历史修订（分区）/ th_trans_head —— 头指针（分区）
    # =====================================================================================
    if dialect == "postgresql":
        # 3.1 rev（父表 + 8 个子分区）
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS th_trans_rev (
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
              PRIMARY KEY (project_id, id),
              CONSTRAINT ck_rev_variant_fmt CHECK (variant_key='-' OR variant_key ~ '^[a-z][a-z0-9_]*=[^;]+(?:;[a-z][a-z0-9_]*=[^;]+)*$'),
              CONSTRAINT ck_rev_bcp47 CHECK (th.is_bcp47(target_lang))
            ) PARTITION BY HASH (project_id);
            """
        )
        for i in range(8):
            op.execute(
                f"""
                CREATE TABLE IF NOT EXISTS th_trans_rev_p{i}
                PARTITION OF th_trans_rev FOR VALUES WITH (MODULUS 8, REMAINDER {i});
                """
            )
            op.execute(
                f"""
                CREATE INDEX IF NOT EXISTS ix_rev_p{i}_content_lang
                ON th_trans_rev_p{i}(content_id, target_lang);
                """
            )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_rev_dim_no
            ON th_trans_rev (project_id, content_id, target_lang, variant_key, revision_no);
            """
        )
        # 派生 project_id（插入时）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.trans_derive_project_rev()
            RETURNS trigger AS $$
            BEGIN
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
        op.execute("DROP TRIGGER IF EXISTS trg_rev_derive_project_ins ON th_trans_rev;")
        op.execute(
            """
            CREATE TRIGGER trg_rev_derive_project_ins
            BEFORE INSERT ON th_trans_rev
            FOR EACH ROW EXECUTE FUNCTION th.trans_derive_project_rev();
            """
        )
        # 语言归一
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.autonorm_bcp47_rev()
            RETURNS trigger AS $$
            BEGIN
              NEW.target_lang := th.bcp47_normalize(NEW.target_lang);
              IF NOT th.is_bcp47(NEW.target_lang) THEN
                RAISE EXCEPTION 'invalid BCP-47: %', NEW.target_lang;
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_rev_bcp47_autonorm ON th_trans_rev;")
        op.execute(
            """
            CREATE TRIGGER trg_rev_bcp47_autonorm
            BEFORE INSERT OR UPDATE OF target_lang ON th_trans_rev
            FOR EACH ROW EXECUTE FUNCTION th.autonorm_bcp47_rev();
            """
        )

        # 3.2 head（父表 + 8 个子分区）
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS th_trans_head (
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
              CONSTRAINT uq_head_dim UNIQUE (project_id, content_id, target_lang, variant_key),
              FOREIGN KEY (project_id, current_rev_id)   REFERENCES th_trans_rev(project_id, id) ON DELETE RESTRICT,
              FOREIGN KEY (project_id, published_rev_id) REFERENCES th_trans_rev(project_id, id) ON DELETE RESTRICT,
              CONSTRAINT uq_head_published_rev UNIQUE (project_id, published_rev_id),
              CONSTRAINT ck_head_variant_fmt CHECK (variant_key='-' OR variant_key ~ '^[a-z][a-z0-9_]*=[^;]+(?:;[a-z][a-z0-9_]*=[^;]+)*$'),
              CONSTRAINT ck_head_bcp47 CHECK (th.is_bcp47(target_lang))
            ) PARTITION BY HASH (project_id);
            """
        )
        for i in range(8):
            op.execute(
                f"""
                CREATE TABLE IF NOT EXISTS th_trans_head_p{i}
                PARTITION OF th_trans_head FOR VALUES WITH (MODULUS 8, REMAINDER {i});
                """
            )
            op.execute(
                f"""
                CREATE INDEX IF NOT EXISTS ix_head_p{i}_proj_lang_status_id
                ON th_trans_head_p{i}(project_id, target_lang, current_status, id);
                """
            )
            op.execute(
                f"""
                CREATE INDEX IF NOT EXISTS ix_head_p{i}_content
                ON th_trans_head_p{i}(project_id, content_id);
                """
            )

        # updated_at
        op.execute("DROP TRIGGER IF EXISTS trg_head_touch_updated_at ON th_trans_head;")
        op.execute(
            """
            CREATE TRIGGER trg_head_touch_updated_at
            BEFORE UPDATE ON th_trans_head
            FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();
            """
        )
        # head.status 一致性校验
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.head_status_guard()
            RETURNS trigger AS $$
            DECLARE rev_status translation_status;
            BEGIN
              SELECT r.status INTO rev_status
              FROM th_trans_rev r
              WHERE r.project_id = NEW.project_id AND r.id = NEW.current_rev_id;

              IF rev_status IS NULL THEN
                RAISE EXCEPTION 'current_rev_id % not found for project %', NEW.current_rev_id, NEW.project_id;
              END IF;

              IF NEW.current_status IS DISTINCT FROM rev_status THEN
                RAISE EXCEPTION 'head.current_status(%) mismatches rev.status(%)',
                  NEW.current_status, rev_status;
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_head_status_guard ON th_trans_head;")
        op.execute(
            """
            CREATE TRIGGER trg_head_status_guard
            BEFORE INSERT OR UPDATE OF current_rev_id, current_status ON th_trans_head
            FOR EACH ROW EXECUTE FUNCTION th.head_status_guard();
            """
        )
        # 语言归一
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.autonorm_bcp47_head()
            RETURNS trigger AS $$
            BEGIN
              NEW.target_lang := th.bcp47_normalize(NEW.target_lang);
              IF NOT th.is_bcp47(NEW.target_lang) THEN
                RAISE EXCEPTION 'invalid BCP-47: %', NEW.target_lang;
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_head_bcp47_autonorm ON th_trans_head;")
        op.execute(
            """
            CREATE TRIGGER trg_head_bcp47_autonorm
            BEFORE INSERT OR UPDATE OF target_lang ON th_trans_head
            FOR EACH ROW EXECUTE FUNCTION th.autonorm_bcp47_head();
            """
        )

        # RLS（USING + WITH CHECK）
        op.execute("ALTER TABLE th_trans_rev  ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE th_trans_head ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_rev_rls  ON th_trans_rev;")
        op.execute("DROP POLICY IF EXISTS p_head_rls ON th_trans_head;")
        op.execute(
            "CREATE POLICY p_rev_rls  ON th_trans_rev  USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )
        op.execute(
            "CREATE POLICY p_head_rls ON th_trans_head USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

        # 存储参数建议（父表）
        op.execute("ALTER TABLE th_trans_rev  SET (fillfactor=90);")
        op.execute("ALTER TABLE th_trans_head SET (fillfactor=90);")
        op.execute("ALTER TABLE th_trans_rev  SET (autovacuum_vacuum_scale_factor=0.1, autovacuum_analyze_scale_factor=0.05);")
        op.execute("ALTER TABLE th_trans_head SET (autovacuum_vacuum_scale_factor=0.1, autovacuum_analyze_scale_factor=0.05);")

        # 同步到所有分区子表
        op.execute(
            """
            DO $$
            DECLARE r RECORD;
            BEGIN
              FOR r IN
                SELECT inhrelid::regclass AS child
                FROM pg_inherits
                WHERE inhparent IN ('th_trans_rev'::regclass, 'th_trans_head'::regclass)
              LOOP
                EXECUTE format('ALTER TABLE %s SET (fillfactor=90, autovacuum_vacuum_scale_factor=0.1, autovacuum_analyze_scale_factor=0.05)', r.child);
              END LOOP;
            END $$;
            """
        )

    else:
        # 非 PostgreSQL：普通表代替（无分区），约束与触发器由应用层兜底
        status_type = sa.Enum("draft", "reviewed", "published", "rejected", name="translation_status")
        op.create_table(
            "th_trans_rev",
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), sa.ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_lang", sa.String(), nullable=False),
            sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
            sa.Column("status", status_type, nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("translated_payload_json", json_type, nullable=True),
            sa.Column("origin_lang", sa.String(), nullable=True),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("lint_report_json", json_type, nullable=True),
            sa.Column("engine_name", sa.String(), nullable=True),
            sa.Column("engine_version", sa.String(), nullable=True),
            sa.Column("prompt_hash", sa.String(), nullable=True),
            sa.Column("params_hash", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("project_id", "id"),
        )
        op.create_index("ix_rev_content_lang", "th_trans_rev", ["content_id", "target_lang"], unique=False)
        op.create_unique_constraint("uq_rev_dim_no", "th_trans_rev", ["project_id", "content_id", "target_lang", "variant_key", "revision_no"])

        op.create_table(
            "th_trans_head",
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("content_id", sa.String(), sa.ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_lang", sa.String(), nullable=False),
            sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
            sa.Column("current_rev_id", sa.String(), nullable=False),
            sa.Column("current_status", status_type, nullable=False),
            sa.Column("current_no", sa.Integer(), nullable=False),
            sa.Column("published_rev_id", sa.String(), nullable=True),
            sa.Column("published_no", sa.Integer(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("project_id", "id"),
        )
        op.create_unique_constraint("uq_head_dim", "th_trans_head", ["project_id", "content_id", "target_lang", "variant_key"])
        op.create_index("ix_head_proj_lang_status_id", "th_trans_head", ["project_id", "target_lang", "current_status", "id"], unique=False)
        op.create_index("ix_head_content", "th_trans_head", ["project_id", "content_id"], unique=False)

    # =====================================================================================
    # 4) 解析缓存 th_resolve_cache（TTL + 发布精准失效）
    # =====================================================================================
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
    op.create_index("ix_resolve_expires", "th_resolve_cache", ["expires_at"], unique=False)
    if dialect == "postgresql":
        # 外键：缓存指向 rev
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='fk_resolve_cache_rev'
              ) THEN
                ALTER TABLE th_resolve_cache
                  ADD CONSTRAINT fk_resolve_cache_rev
                  FOREIGN KEY (project_id, resolved_rev)
                  REFERENCES th_trans_rev(project_id, id)
                  ON DELETE CASCADE;
              END IF;
            END $$;
            """
        )
        # 项目级默认 TTL
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.resolve_default_ttl(p_project_id TEXT)
            RETURNS INT AS $$
            DECLARE v INT;
            BEGIN
              SELECT COALESCE((settings_json->>'resolve_ttl_seconds')::INT, 60)
                INTO v FROM th_projects WHERE project_id=p_project_id;
              RETURN COALESCE(v, 60);
            END; $$ LANGUAGE plpgsql STABLE;
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.res_cache_default_expiry()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.expires_at IS NULL THEN
                NEW.expires_at := CURRENT_TIMESTAMP + make_interval(secs => th.resolve_default_ttl(NEW.project_id));
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_resolve_cache_default_expiry ON th_resolve_cache;")
        op.execute(
            """
            CREATE TRIGGER trg_resolve_cache_default_expiry
            BEFORE INSERT ON th_resolve_cache
            FOR EACH ROW EXECUTE FUNCTION th.res_cache_default_expiry();
            """
        )
        # 发布指针变更 → 精准失效
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.resolve_cache_invalidate_on_publish()
            RETURNS trigger AS $$
            BEGIN
              IF (OLD.published_rev_id IS DISTINCT FROM NEW.published_rev_id) THEN
                DELETE FROM th_resolve_cache
                 WHERE content_id = NEW.content_id
                   AND target_lang = NEW.target_lang
                   AND variant_key = NEW.variant_key;
              END IF; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_head_invalidate_resolve_cache ON th_trans_head;")
        op.execute(
            """
            CREATE TRIGGER trg_head_invalidate_resolve_cache
            AFTER UPDATE OF published_rev_id ON th_trans_head
            FOR EACH ROW EXECUTE FUNCTION th.resolve_cache_invalidate_on_publish();
            """
        )
        # RLS（USING + WITH CHECK）
        op.execute("ALTER TABLE th_resolve_cache ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_resolve_rls ON th_resolve_cache;")
        op.execute(
            """
            CREATE POLICY p_resolve_rls ON th_resolve_cache
            USING (project_id = ANY (th.allowed_projects()))
            WITH CHECK (project_id = ANY (th.allowed_projects()));
            """
        )

    # =====================================================================================
    # 5) 影子索引（最小占位 + 注册表 + ETL 状态）
    # =====================================================================================
    op.create_table(
        "search_content",
        sa.Column("content_id", sa.String(), sa.ForeignKey("th_content.id", ondelete="CASCADE"), primary_key=True, comment="最小占位：不预置镜像列"),
    )
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.sc_minimal_touch()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP='DELETE' THEN
                DELETE FROM search_content WHERE content_id=OLD.id; RETURN OLD;
              END IF;
              INSERT INTO search_content(content_id) VALUES (NEW.id)
              ON CONFLICT (content_id) DO NOTHING; RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        for trig, event in (
            ("trg_sc_ins",  "AFTER INSERT"),
            ("trg_sc_upd",  "AFTER UPDATE OF keys_json, namespace, project_id"),
            ("trg_sc_del",  "AFTER DELETE"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trig} ON th_content;")
        op.execute(
            "CREATE TRIGGER trg_sc_ins AFTER INSERT ON th_content FOR EACH ROW EXECUTE FUNCTION th.sc_minimal_touch();"
        )
        op.execute(
            "CREATE TRIGGER trg_sc_upd AFTER UPDATE OF keys_json, namespace, project_id ON th_content FOR EACH ROW EXECUTE FUNCTION th.sc_minimal_touch();"
        )
        op.execute(
            "CREATE TRIGGER trg_sc_del AFTER DELETE ON th_content FOR EACH ROW EXECUTE FUNCTION th.sc_minimal_touch();"
        )

    op.create_table(
        "th_search_columns_registry",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("column_name", sa.String(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False, comment="JSONPath/键路径，如 $.keys_json.route"),
        sa.Column("data_type", sa.String(), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("indexed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("unique_hint", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.create_check_constraint(
            "ck_search_col_datatype",
            "th_search_columns_registry",
            "data_type IN ('text','int','bool','timestamp')",
        )
        # RLS（USING + WITH CHECK）
        op.execute("ALTER TABLE th_search_columns_registry ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_search_col_rls ON th_search_columns_registry;")
        op.execute(
            "CREATE POLICY p_search_col_rls ON th_search_columns_registry USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

    op.create_table(
        "th_search_etl_state",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), primary_key=True),
        sa.Column("last_content_touch", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_full_rebuild", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.execute("ALTER TABLE th_search_etl_state ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_search_etl_rls ON th_search_etl_state;")
        op.execute(
            "CREATE POLICY p_search_etl_rls ON th_search_etl_state USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

    # =====================================================================================
    # 6) TM 与追溯
    # =====================================================================================
    op.create_table(
        "th_tm",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("reuse_sha256_bytes", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_text_json", json_type, nullable=False),
        sa.Column("translated_json", json_type, nullable=False),
        sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'")),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("visibility_scope", sa.String(), nullable=False, server_default=sa.text("'project'")),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("hash_algo_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("reuse_policy_fingerprint", sa.String(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("pii_flags", json_type, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "namespace", "reuse_sha256_bytes", "source_lang", "target_lang", "variant_key", "policy_version", "hash_algo_version", name="uq_tm_reuse_key"),
    )
    if dialect == "postgresql":
        op.create_check_constraint("ck_tm_reuse_sha256_len", "th_tm", "octet_length(reuse_sha256_bytes)=32")
        op.create_check_constraint("ck_tm_visibility_scope", "th_tm", "visibility_scope IN ('project','tenant','global')")
        op.execute("DROP TRIGGER IF EXISTS trg_tm_touch_updated_at ON th_tm;")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.tm_touch_updated_at()
            RETURNS trigger AS $$
            BEGIN NEW.updated_at = CURRENT_TIMESTAMP; RETURN NEW; END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_tm_touch_updated_at
            BEFORE UPDATE ON th_tm FOR EACH ROW EXECUTE FUNCTION th.tm_touch_updated_at();
            """
        )
        # RLS
        op.execute("ALTER TABLE th_tm ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_tm_rls ON th_tm;")
        op.execute(
            "CREATE POLICY p_tm_rls ON th_tm USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )
    op.create_index("ix_tm_last_used", "th_tm", ["last_used_at"], unique=False)

    op.create_table(
        "th_tm_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("translation_rev_id", sa.String(), nullable=False),
        sa.Column("tm_id", sa.String(), sa.ForeignKey("th_tm.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("project_id", "translation_rev_id", "tm_id", name="uq_tm_links_triplet"),
    )
    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE th_tm_links
            ADD CONSTRAINT fk_tm_links_rev
            FOREIGN KEY (project_id, translation_rev_id)
            REFERENCES th_trans_rev(project_id, id)
            ON DELETE CASCADE;
            """
        )
        op.execute("ALTER TABLE th_tm_links ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_tm_links_rls ON th_tm_links;")
        op.execute(
            "CREATE POLICY p_tm_links_rls ON th_tm_links USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

    # =====================================================================================
    # 7) 语言回退策略
    # =====================================================================================
    op.create_table(
        "th_locales_fallbacks",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column("fallback_order", json_type, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("project_id", "locale"),
    )
    if dialect == "postgresql":
        op.create_check_constraint("ck_fallbacks_json_array", "th_locales_fallbacks", "jsonb_typeof(fallback_order)='array'")
        # 归一化 + 更新 updated_at
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.autonorm_bcp47_fallbacks()
            RETURNS trigger AS $$
            BEGIN
              NEW.locale := th.bcp47_normalize(NEW.locale);
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_fallbacks_bcp47_autonorm ON th_locales_fallbacks;")
        op.execute(
            """
            CREATE TRIGGER trg_fallbacks_bcp47_autonorm
            BEFORE INSERT OR UPDATE OF locale ON th_locales_fallbacks
            FOR EACH ROW EXECUTE FUNCTION th.autonorm_bcp47_fallbacks();
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_fallbacks_touch ON th_locales_fallbacks;")
        op.execute(
            """
            CREATE TRIGGER trg_fallbacks_touch
            BEFORE UPDATE ON th_locales_fallbacks
            FOR EACH ROW EXECUTE FUNCTION th.set_updated_at();
            """
        )
        # RLS
        op.execute("ALTER TABLE th_locales_fallbacks ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_fallbacks_rls ON th_locales_fallbacks;")
        op.execute(
            "CREATE POLICY p_fallbacks_rls ON th_locales_fallbacks USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )
    # =====================================================================================
    # 8) 事件与评论（事件类型白名单 + 索引）
    # =====================================================================================
    op.create_table(
        "th_trans_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("head_id", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE th_trans_events
              ADD CONSTRAINT ck_events_type_whitelist
              CHECK (event_type IN (
                'submit','ai_suggest','tm_apply','edit_human','review_request',
                'review_approve','review_reject','publish','unpublish','rollback',
                'lint_pass','lint_fail','auto_fix_applied','term_update',
                'cache_invalidate','import','export','sync_shadow','reindex'
              ));
            """
        )
        op.execute(
            """
            ALTER TABLE th_trans_events
              ADD CONSTRAINT fk_events_head
              FOREIGN KEY (project_id, head_id)
              REFERENCES th_trans_head(project_id, id)
              ON DELETE CASCADE;
            """
        )
        # 索引（PG：带 DESC）
        op.execute("CREATE INDEX IF NOT EXISTS ix_events_project_time ON th_trans_events (project_id, created_at DESC)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_events_head_time    ON th_trans_events (head_id,    created_at DESC)")
        # RLS
        op.execute("ALTER TABLE th_trans_events ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_events_rls ON th_trans_events;")
        op.execute(
            "CREATE POLICY p_events_rls ON th_trans_events USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )
    else:
        # 非 PG：用普通索引代替（不带 DESC）
        op.create_index("ix_events_project_time", "th_trans_events", ["project_id", "created_at"], unique=False)
        op.create_index("ix_events_head_time",    "th_trans_events", ["head_id",    "created_at"], unique=False)

    op.create_table(
        "th_trans_comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("head_id", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE th_trans_comments
              ADD CONSTRAINT fk_comments_head
              FOREIGN KEY (project_id, head_id)
              REFERENCES th_trans_head(project_id, id)
              ON DELETE CASCADE;
            """
        )
        op.execute("ALTER TABLE th_trans_comments ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_comments_rls ON th_trans_comments;")
        op.execute(
            "CREATE POLICY p_comments_rls ON th_trans_comments USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

    # =====================================================================================
    # 9) 术语：别名/使用 + 四层唯一护栏（表达式索引）
    # =====================================================================================
    op.create_table(
        "th_term_aliases",
        sa.Column("term_key", sa.String(), nullable=False),
        sa.Column("alias_text", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("term_key", "alias_text"),
    )
    op.create_table(
        "th_term_usage",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("content_id", sa.String(), sa.ForeignKey("th_content.id", ondelete="CASCADE"), nullable=False),
        sa.Column("term_key", sa.String(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("project_id", "content_id", "term_key"),
    )
    if dialect == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_term_global_key
              ON th_content ((keys_json->>'term_key'))
            WHERE namespace='common.glossary.term.v1'
              AND keys_json->>'scope'='global';
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_term_mod_key
              ON th_content ((keys_json->>'term_key'), (keys_json->>'mod_id'))
            WHERE namespace='common.glossary.term.v1'
              AND keys_json->>'scope'='mod';
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_term_pack_key
              ON th_content ((keys_json->>'term_key'), (keys_json->>'pack_id'))
            WHERE namespace='common.glossary.term.v1'
              AND keys_json->>'scope'='pack';
            """
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_term_project_key
              ON th_content ((keys_json->>'term_key'), (keys_json->>'project_id'))
            WHERE namespace='common.glossary.term.v1'
              AND keys_json->>'scope'='project';
            """
        )

    # =====================================================================================
    # 10) 规则包（分层/灰度）与运行记录
    # =====================================================================================
    op.create_table(
        "th_rulesets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scope_level", sa.String(), nullable=False),
        sa.Column("scope_ref", sa.String(), nullable=True),
        sa.Column("rule_key", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("selector", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=True),
        sa.Column("filetag", sa.String(), nullable=True),
        sa.Column("target_lang", sa.String(), nullable=True),
        sa.Column("pattern", sa.String(), nullable=True),
        sa.Column("fix_action", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version_tag", sa.String(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollout_percent", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("parent_ruleset_id", sa.String(), nullable=True),
        sa.Column("hash_fingerprint", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.create_check_constraint("ck_rules_scope_level", "th_rulesets", "scope_level IN ('global','platform','tenant','project','namespace','filetag','lang')")
        op.create_check_constraint("ck_rules_severity", "th_rulesets", "severity IN ('error','warn','info')")
        op.create_check_constraint("ck_rules_selector", "th_rulesets", "selector IN ('source','translation','both')")
        op.create_check_constraint("ck_rules_rollout", "th_rulesets", "rollout_percent BETWEEN 0 AND 100")
        op.create_unique_constraint("uq_rules_logic", "th_rulesets", ["scope_level","scope_ref","rule_key","version_tag"])

    op.create_table(
        "th_rules_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("head_id", sa.String(), nullable=False),
        sa.Column("rev_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),  # passed/failed/auto_fixed
        sa.Column("report_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    if dialect == "postgresql":
        op.execute("ALTER TABLE th_rules_runs ENABLE ROW LEVEL SECURITY;")
        op.execute("DROP POLICY IF EXISTS p_rules_runs_rls ON th_rules_runs;")
        op.execute(
            "CREATE POLICY p_rules_runs_rls ON th_rules_runs USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
        )

    # =====================================================================================
    # 11) 变体策略（顺序/白名单/冲突/必填） + 规范化函数与触发器
    # =====================================================================================
    op.create_table(
        "th_variant_order",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("dim", sa.String(), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "dim"),
    )
    if dialect == "postgresql":
        op.create_unique_constraint("uq_variant_order_no", "th_variant_order", ["project_id","order_no"])

    op.create_table(
        "th_variant_whitelist",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("dim", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "dim", "value"),
    )

    op.create_table(
        "th_variant_conflicts",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("if_dim", sa.String(), nullable=False),
        sa.Column("if_value", sa.String(), nullable=False),
        sa.Column("deny_dim", sa.String(), nullable=False),
        sa.Column("deny_value", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "rule_id"),
    )

    op.create_table(
        "th_variant_require",
        sa.Column("project_id", sa.String(), sa.ForeignKey("th_projects.project_id"), nullable=False),
        sa.Column("dim", sa.String(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("project_id", "dim"),
    )

    if dialect == "postgresql":
        # 规范化函数 —— 标注 STABLE（读取表数据，不能 IMMUTABLE）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.variant_canonicalize(p_project_id TEXT, p_vk TEXT)
            RETURNS TEXT AS $$
            DECLARE
              kv TEXT; k TEXT; v TEXT; arr TEXT[];
              pairs TEXT[] := '{}'::TEXT[];
              out_pairs TEXT := '';
              used_dims TEXT[] := '{}'::TEXT[];
              ord RECORD; has_any BOOLEAN := FALSE;
            BEGIN
              IF p_vk IS NULL OR btrim(p_vk) = '' OR p_vk = '-' THEN
                RETURN '-';
              END IF;
              arr := regexp_split_to_array(p_vk, '\\s*;\\s*');
              FOREACH kv IN ARRAY arr LOOP
                IF kv = '' THEN CONTINUE; END IF;
                k := split_part(kv, '=', 1); v := split_part(kv, '=', 2); k := lower(k);
                IF k !~ '^[a-z][a-z0-9_]*$' THEN RAISE EXCEPTION 'variant_key: invalid dim: %', k; END IF;
                IF k = '' OR v = '' THEN RAISE EXCEPTION 'variant_key: invalid pair: %', kv; END IF;
                IF EXISTS (SELECT 1 FROM th_variant_whitelist w WHERE w.project_id=p_project_id AND w.dim=k) THEN
                  IF NOT EXISTS (SELECT 1 FROM th_variant_whitelist w WHERE w.project_id=p_project_id AND w.dim=k AND w.value=v) THEN
                    RAISE EXCEPTION 'variant_key: value % not allowed on dim %', v, k;
                  END IF;
                END IF;
                pairs := array_remove(pairs, k);
                pairs := pairs || (k || '=' || v);
                used_dims := array_remove(used_dims, k);
                used_dims := used_dims || k;
              END LOOP;
              FOR ord IN SELECT dim FROM th_variant_require WHERE project_id=p_project_id AND required=TRUE LOOP
                IF NOT ord.dim = ANY(used_dims) THEN
                  RAISE EXCEPTION 'variant_key: missing required dim %', ord.dim;
                END IF;
              END LOOP;
              FOR ord IN SELECT dim FROM th_variant_order WHERE project_id=p_project_id ORDER BY order_no LOOP
                FOREACH kv IN ARRAY pairs LOOP
                  k := split_part(kv, '=', 1);
                  IF k = ord.dim THEN
                    out_pairs := out_pairs || CASE WHEN out_pairs = '' THEN '' ELSE ';' END || kv;
                    has_any := TRUE;
                  END IF;
                END LOOP;
              END LOOP;
              FOREACH kv IN ARRAY (SELECT array_agg(p ORDER BY p) FROM unnest(pairs) p) LOOP
                k := split_part(kv, '=', 1);
                IF NOT EXISTS (SELECT 1 FROM th_variant_order WHERE project_id=p_project_id AND dim=k) THEN
                  out_pairs := out_pairs || CASE WHEN out_pairs = '' THEN '' ELSE ';' END || kv;
                  has_any := TRUE;
                END IF;
              END LOOP;
              IF NOT has_any THEN RETURN '-'; END IF;
              RETURN out_pairs;
            END; $$ LANGUAGE plpgsql STABLE;
            """
        )
        # 自动规范化（rev/head）
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.variant_autonorm_rev()
            RETURNS trigger AS $$
            BEGIN
              NEW.variant_key := th.variant_canonicalize(NEW.project_id, NEW.variant_key);
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_rev_variant_autonorm ON th_trans_rev;")
        op.execute(
            """
            CREATE TRIGGER trg_rev_variant_autonorm
            BEFORE INSERT OR UPDATE OF variant_key, project_id ON th_trans_rev
            FOR EACH ROW EXECUTE FUNCTION th.variant_autonorm_rev();
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th.variant_autonorm_head()
            RETURNS trigger AS $$
            BEGIN
              NEW.variant_key := th.variant_canonicalize(NEW.project_id, NEW.variant_key);
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            """
        )
        op.execute("DROP TRIGGER IF EXISTS trg_head_variant_autonorm ON th_trans_head;")
        op.execute(
            """
            CREATE TRIGGER trg_head_variant_autonorm
            BEFORE INSERT OR UPDATE OF variant_key, project_id ON th_trans_head
            FOR EACH ROW EXECUTE FUNCTION th.variant_autonorm_head();
            """
        )

    # =====================================================================================
    # 12) RLS：确保核心表已开启并具备 WITH CHECK（上面已分别处理，这里兜底）
    # =====================================================================================
    if dialect == "postgresql":
        for tbl, pol in (
            ("th_content", "p_content_rls"),
            ("th_trans_rev", "p_rev_rls"),
            ("th_trans_head", "p_head_rls"),
            ("th_resolve_cache", "p_resolve_rls"),
        ):
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"DROP POLICY IF EXISTS {pol} ON {tbl};")
            op.execute(
                f"CREATE POLICY {pol} ON {tbl} USING (project_id = ANY (th.allowed_projects())) WITH CHECK (project_id = ANY (th.allowed_projects()));"
            )

    # 迁移结束
    # =====================================================================================


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 规则与术语
    op.execute("DROP TABLE IF EXISTS th_rules_runs")
    op.execute("DROP TABLE IF EXISTS th_rulesets")

    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_term_project_key")
        op.execute("DROP INDEX IF EXISTS uq_term_pack_key")
        op.execute("DROP INDEX IF EXISTS uq_term_mod_key")
        op.execute("DROP INDEX IF EXISTS uq_term_global_key")

    op.execute("DROP TABLE IF EXISTS th_term_usage")
    op.execute("DROP TABLE IF EXISTS th_term_aliases")

    # 事件与评论
    if dialect == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_events_head_time")
        op.execute("DROP INDEX IF EXISTS ix_events_project_time")
        op.execute("ALTER TABLE IF EXISTS th_trans_events DROP CONSTRAINT IF EXISTS fk_events_head")
        op.execute("ALTER TABLE IF EXISTS th_trans_events DROP CONSTRAINT IF EXISTS ck_events_type_whitelist")
    else:
        # 非 PG 的普通索引名同上
        op.execute("DROP INDEX IF EXISTS ix_events_head_time")
        op.execute("DROP INDEX IF EXISTS ix_events_project_time")
    op.execute("DROP TABLE IF EXISTS th_trans_comments")
    op.execute("DROP TABLE IF EXISTS th_trans_events")

    # 语言回退
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_fallbacks_touch ON th_locales_fallbacks")
        op.execute("DROP TRIGGER IF EXISTS trg_fallbacks_bcp47_autonorm ON th_locales_fallbacks")
        op.execute("DROP FUNCTION IF EXISTS th.autonorm_bcp47_fallbacks()")
    op.execute("DROP TABLE IF EXISTS th_locales_fallbacks")

    # TM
    if dialect == "postgresql":
        op.execute("ALTER TABLE IF EXISTS th_tm_links DROP CONSTRAINT IF EXISTS fk_tm_links_rev")
    op.execute("DROP TABLE IF EXISTS th_tm_links")
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_tm_touch_updated_at ON th_tm")
        op.execute("DROP FUNCTION IF EXISTS th.tm_touch_updated_at()")
    op.execute("DROP INDEX IF EXISTS ix_tm_last_used")
    op.execute("DROP TABLE IF EXISTS th_tm")

    # 影子索引
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_sc_del ON th_content")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_upd ON th_content")
        op.execute("DROP TRIGGER IF EXISTS trg_sc_ins ON th_content")
        op.execute("DROP FUNCTION IF EXISTS th.sc_minimal_touch()")
    op.execute("DROP TABLE IF EXISTS th_search_etl_state")
    op.execute("DROP TABLE IF EXISTS th_search_columns_registry")
    op.execute("DROP TABLE IF EXISTS search_content")

    # 解析缓存
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_head_invalidate_resolve_cache ON th_trans_head")
        op.execute("DROP FUNCTION IF EXISTS th.resolve_cache_invalidate_on_publish()")
        op.execute("DROP TRIGGER IF EXISTS trg_resolve_cache_default_expiry ON th_resolve_cache")
        op.execute("DROP FUNCTION IF EXISTS th.res_cache_default_expiry()")
        op.execute("DROP FUNCTION IF EXISTS th.resolve_default_ttl(TEXT)")
        op.execute("ALTER TABLE IF EXISTS th_resolve_cache DROP CONSTRAINT IF EXISTS fk_resolve_cache_rev")
    op.execute("DROP INDEX IF EXISTS ix_resolve_expires")
    op.execute("DROP INDEX IF EXISTS ix_resolve_project")
    op.execute("DROP TABLE IF EXISTS th_resolve_cache")

    # 变体策略
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_head_variant_autonorm ON th_trans_head")
        op.execute("DROP FUNCTION IF EXISTS th.variant_autonorm_head()")
        op.execute("DROP TRIGGER IF EXISTS trg_rev_variant_autonorm ON th_trans_rev")
        op.execute("DROP FUNCTION IF EXISTS th.variant_autonorm_rev()")
        op.execute("DROP FUNCTION IF EXISTS th.variant_canonicalize(TEXT, TEXT)")
    op.execute("DROP TABLE IF EXISTS th_variant_require")
    op.execute("DROP TABLE IF EXISTS th_variant_conflicts")
    op.execute("DROP TABLE IF EXISTS th_variant_whitelist")
    if dialect == "postgresql":
        op.execute("ALTER TABLE IF EXISTS th_variant_order DROP CONSTRAINT IF EXISTS uq_variant_order_no")
    op.execute("DROP TABLE IF EXISTS th_variant_order")

    # head / rev
    if dialect == "postgresql":
        for i in range(8):
            op.execute(f"DROP TABLE IF EXISTS th_trans_head_p{i} CASCADE")
        op.execute("DROP TABLE IF EXISTS th_trans_head CASCADE")

        for i in range(8):
            op.execute(f"DROP TABLE IF EXISTS th_trans_rev_p{i} CASCADE")
        op.execute("DROP TABLE IF EXISTS th_trans_rev CASCADE")

        op.execute("DROP TRIGGER IF EXISTS trg_head_bcp47_autonorm ON th_trans_head")
        op.execute("DROP FUNCTION IF EXISTS th.autonorm_bcp47_head()")
        op.execute("DROP TRIGGER IF EXISTS trg_head_status_guard ON th_trans_head")
        op.execute("DROP FUNCTION IF EXISTS th.head_status_guard()")
        op.execute("DROP TRIGGER IF EXISTS trg_head_touch_updated_at ON th_trans_head")

        op.execute("DROP TRIGGER IF EXISTS trg_rev_bcp47_autonorm ON th_trans_rev")
        op.execute("DROP FUNCTION IF EXISTS th.autonorm_bcp47_rev()")
        op.execute("DROP TRIGGER IF EXISTS trg_rev_derive_project_ins ON th_trans_rev")
        op.execute("DROP FUNCTION IF EXISTS th.trans_derive_project_rev()")
    else:
        op.execute("DROP TABLE IF EXISTS th_trans_head")
        op.execute("DROP TABLE IF EXISTS th_trans_rev")

    # content
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_content_touch_updated_at ON th_content")
        op.execute("DROP TRIGGER IF EXISTS trg_content_forbid_uida_update ON th_content")
        op.execute("DROP FUNCTION IF EXISTS th.content_forbid_uida_update()")
    op.execute("DROP INDEX IF EXISTS ix_content_proj_ns_ver")
    op.execute("DROP INDEX IF EXISTS ix_content_proj_ns")
    op.execute("DROP TABLE IF EXISTS th_content")

    # projects
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_projects_touch_updated_at ON th_projects")
        op.execute("DROP TRIGGER IF EXISTS trg_projects_forbid_rename ON th_projects")
        op.execute("DROP FUNCTION IF EXISTS th.projects_forbid_rename()")
    op.execute("DROP TABLE IF EXISTS th_projects")

    # 公共对象
    if dialect == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS th.allowed_projects()")
        op.execute("DROP FUNCTION IF EXISTS th.bcp47_normalize(TEXT)")
        op.execute("DROP FUNCTION IF EXISTS th.is_bcp47(TEXT)")
        op.execute("DROP FUNCTION IF EXISTS public.is_bcp47(TEXT)")
        op.execute("DROP FUNCTION IF EXISTS th.set_updated_at()")
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname='translation_status') THEN DROP TYPE translation_status; END IF; END $$;")
        op.execute("DROP SCHEMA IF EXISTS th CASCADE")
