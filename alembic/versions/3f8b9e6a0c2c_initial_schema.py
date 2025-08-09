# alembic/versions/3f8b9e6a0c2c_initial_schema.py
# [v1.2.1 - Idempotency Fix]
"""
TRANS-HUB 数据库初始架构（Final v1.2 · UIDA 版）

Revision ID: 3f8b9e6a0c2c
Revises:
Create Date: 2024-05-22 11:30:00.000000

本迁移脚本实现白皮书（Final v1.2）所述的最小完备数据模型：
- th_content：源内容权威，UIDA=(project_id, namespace, keys_sha256_bytes) 唯一
- th_translations：按语言/变体的权威译文；同(content_id,target_lang,variant_key)仅允许一条已发布
- th_tm：翻译记忆仓；th_tm_links：复用追溯（译文 ↔ TM）
- th_locales_fallbacks：项目级语言回退策略
- 触发器（PostgreSQL）：UIDA 三元不可变；translations.project_id 由 content 派生；updated_at 自动更新

兼容说明：
- 以 PostgreSQL 为主；SQLite 分支避免使用不支持的方言特性，并用等效 SQL 兜底（如局部唯一索引）。
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
    根据方言选择 JSON 类型：PostgreSQL 使用 JSONB，其它方言使用通用 JSON。
    """
    if dialect_name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    JSONType = _json_type(dialect)

    # ----------------------------------------------------------------------
    # 0) 定义枚举：译文状态（仅 4 种）
    #    [v1.2.1 Idempotency Fix] SQLAlchemy's op.create_table will handle
    #    the creation of the ENUM type implicitly. The explicit create call
    #    is redundant and causes errors in test lifecycles.
    # ----------------------------------------------------------------------
    translation_status = sa.Enum(
        "draft", "reviewed", "published", "rejected", name="translation_status"
    )
    # The following line is removed as it is redundant.
    # translation_status.create(bind, checkfirst=True)

    # ----------------------------------------------------------------------
    # 1) th_content：源内容权威
    # ----------------------------------------------------------------------
    op.create_table(
        "th_content",
        sa.Column("id", sa.String(), nullable=False, comment="主键（无业务含义，字符串 UUID 或雪花 ID）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="项目/租户标识（稳定，不随端/版本改变）"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容域 + 语义版本（如 ui.button.label.v1）"),
        sa.Column(
            "keys_sha256_bytes",
            sa.LargeBinary(length=32),
            nullable=False,
            comment="SHA-256(JCS(keys)) 的 32 字节摘要（唯一事实的一部分）",
        ),
        sa.Column("keys_b64", sa.Text(), nullable=False, comment="JCS(keys) 的 Base64URL 文本（便于跨系统对齐/导出）"),
        sa.Column("keys_json_debug", sa.Text(), nullable=True, comment="JCS(keys) 原始 JSON 文本（仅用于调试）"),
        sa.Column("source_payload_json", JSONType, nullable=False, comment="原文及元数据（结构化 JSON）"),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="业务侧内容版本号"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True, comment="归档时间；历史/下线内容打标"),
        sa.Column("content_type", sa.String(), nullable=True, comment="可选：text/image/audio/file 等"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "namespace", "keys_sha256_bytes", name="uq_content_uida"),
        sa.CheckConstraint(
            "(octet_length(keys_sha256_bytes)=32) OR (length(keys_sha256_bytes)=32)",
            name="ck_content_keys_sha256_len",
        ),
    )

    op.create_index(
        "ix_content_project_namespace",
        "th_content",
        ["project_id", "namespace"],
        unique=False,
    )
    op.create_index(
        "ix_content_project_namespace_version",
        "th_content",
        ["project_id", "namespace", "content_version"],
        unique=False,
    )

    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_content_forbid_uida_update()
            RETURNS trigger AS $$
            BEGIN
                IF (OLD.project_id IS DISTINCT FROM NEW.project_id)
                   OR (OLD.namespace IS DISTINCT FROM NEW.namespace)
                   OR (OLD.keys_sha256_bytes IS DISTINCT FROM NEW.keys_sha256_bytes) THEN
                    RAISE EXCEPTION 'UIDA fields are immutable and cannot be updated';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_content_forbid_uida_update
            BEFORE UPDATE ON th_content
            FOR EACH ROW
            EXECUTE FUNCTION th_content_forbid_uida_update();
            """
        )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS trigger AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_content_touch_updated_at
            BEFORE UPDATE ON th_content
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )

    # ----------------------------------------------------------------------
    # 2) th_translations：译文权威
    # ----------------------------------------------------------------------
    op.create_table(
        "th_translations",
        sa.Column("id", sa.String(), nullable=False, comment="主键（无业务含义，字符串 UUID 或雪花 ID）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="冗余自 th_content.project_id（PG 下触发器派生）"),
        sa.Column("content_id", sa.String(), nullable=False, comment="FK → th_content.id"),
        sa.Column("source_lang", sa.String(), nullable=True, comment="源语言（可选）"),
        sa.Column("target_lang", sa.String(), nullable=False, comment="目标语言（BCP-47，如 zh-CN、en-GB）"),
        sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'"), comment="语言内变体，无则 '-'"),
        sa.Column("status", translation_status, nullable=False, comment="draft|reviewed|published|rejected"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="同维度修订号（编辑 +1）"),
        sa.Column("translated_payload_json", JSONType, nullable=True, comment="结构化译文及元数据"),
        sa.Column("origin_lang", sa.String(), nullable=True, comment="若来自语言回退，记录来源语言"),
        sa.Column("quality_score", sa.Float(), nullable=True, comment="质量评分（可选）"),
        sa.Column("lint_report_json", JSONType, nullable=True, comment="质量/Lint 报告（可选）"),
        sa.Column("engine_name", sa.String(), nullable=True, comment="引擎名称（可选）"),
        sa.Column("engine_version", sa.String(), nullable=True, comment="引擎版本（可选）"),
        sa.Column("prompt_hash", sa.String(), nullable=True, comment="提示词散列（可选）"),
        sa.Column("params_hash", sa.String(), nullable=True, comment="参数散列（可选）"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, comment="发布时刻（仅发布态有值）"),
        sa.Column("published_revision", sa.Integer(), nullable=True, comment="处于发布态时的修订号快照"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["th_content.id"],
            name="fk_trans_content",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_id", "target_lang", "variant_key", "revision",
            name="uq_translations_revision",
        ),
    )

    op.create_index(
        "ix_trans_content_lang",
        "th_translations",
        ["content_id", "target_lang"],
        unique=False,
    )
    op.create_index(
        "ix_trans_lang_status",
        "th_translations",
        ["target_lang", "status"],
        unique=False,
    )
    op.create_index(
        "ix_trans_project_lang_status",
        "th_translations",
        ["project_id", "target_lang", "status"],
        unique=False,
    )

    if dialect == "postgresql":
        op.create_index(
            "uq_translations_published",
            "th_translations",
            ["content_id", "target_lang", "variant_key"],
            unique=True,
            postgresql_where=sa.text("status = 'published'"),
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_translations_published "
            "ON th_translations(content_id, target_lang, variant_key) "
            "WHERE status = 'published';"
        )

    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION th_trans_derive_project()
            RETURNS trigger AS $$
            BEGIN
                SELECT c.project_id INTO NEW.project_id
                FROM th_content c
                WHERE c.id = NEW.content_id;

                IF NEW.project_id IS NULL THEN
                    RAISE EXCEPTION 'content_id % not found when deriving project_id', NEW.content_id;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_trans_derive_project_ins
            BEFORE INSERT ON th_translations
            FOR EACH ROW
            EXECUTE FUNCTION th_trans_derive_project();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_trans_derive_project_upd
            BEFORE UPDATE OF content_id ON th_translations
            FOR EACH ROW
            EXECUTE FUNCTION th_trans_derive_project();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_trans_touch_updated_at
            BEFORE UPDATE ON th_translations
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )

    # ----------------------------------------------------------------------
    # 3) th_tm：翻译记忆仓
    # ----------------------------------------------------------------------
    op.create_table(
        "th_tm",
        sa.Column("id", sa.String(), nullable=False, comment="主键（无业务含义，字符串 UUID 或雪花 ID）"),
        sa.Column("project_id", sa.String(), nullable=False, comment="项目/租户标识"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容域 + 语义版本"),
        sa.Column(
            "reuse_sha256_bytes",
            sa.LargeBinary(length=32),
            nullable=False,
            comment="复用键摘要（降维 keys + 源文本归一化 → SHA-256 32字节）",
        ),
        sa.Column("source_text_json", JSONType, nullable=False, comment="归一化后的源文本骨架/占位符"),
        sa.Column("translated_json", JSONType, nullable=False, comment="结构化可复用译文"),
        sa.Column("variant_key", sa.String(), nullable=False, server_default=sa.text("'-'"), comment="语言内变体"),
        sa.Column("source_lang", sa.String(), nullable=False, comment="源语言"),
        sa.Column("target_lang", sa.String(), nullable=False, comment="目标语言"),
        sa.Column(
            "visibility_scope",
            sa.String(),
            nullable=False,
            server_default=sa.text("'project'"),
            comment="复用可见域：project|tenant|global",
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="复用策略版本"),
        sa.Column("hash_algo_version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="哈希/归一化算法版本"),
        sa.Column("reuse_policy_fingerprint", sa.String(), nullable=True, comment="策略指纹（可选）"),
        sa.Column("quality_score", sa.Float(), nullable=True, comment="质量评分（可选）"),
        sa.Column("pii_flags", JSONType, nullable=True, comment="敏感/隐私标记（可选）"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True, comment="最近复用时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "namespace",
            "reuse_sha256_bytes",
            "source_lang",
            "target_lang",
            "variant_key",
            "policy_version",
            "hash_algo_version",
            name="uq_tm_reuse_key",
        ),
        sa.CheckConstraint(
            "visibility_scope in ('project','tenant','global')",
            name="ck_tm_visibility_scope",
        ),
        sa.CheckConstraint(
            "(octet_length(reuse_sha256_bytes)=32) OR (length(reuse_sha256_bytes)=32)",
            name="ck_tm_reuse_sha256_len",
        ),
    )

    op.create_index("ix_tm_last_used", "th_tm", ["last_used_at"], unique=False)

    if dialect == "postgresql":
        op.execute(
            """
            CREATE TRIGGER trg_tm_touch_updated_at
            BEFORE UPDATE ON th_tm
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
            """
        )

    # ----------------------------------------------------------------------
    # 4) th_tm_links：复用追溯（译文 ↔ TM）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_tm_links",
        sa.Column("id", sa.String(), nullable=False, comment="主键（无业务含义，字符串 UUID 或雪花 ID）"),
        sa.Column("translation_id", sa.String(), nullable=False, comment="FK → th_translations.id"),
        sa.Column("tm_id", sa.String(), nullable=False, comment="FK → th_tm.id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["translation_id"],
            ["th_translations.id"],
            name="fk_tm_links_translation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tm_id"],
            ["th_tm.id"],
            name="fk_tm_links_tm",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("translation_id", "tm_id", name="uq_tm_links_pair"),
    )

    # ----------------------------------------------------------------------
    # 5) th_locales_fallbacks：语言回退策略（项目级）
    # ----------------------------------------------------------------------
    op.create_table(
        "th_locales_fallbacks",
        sa.Column("project_id", sa.String(), nullable=False, comment="项目/租户标识"),
        sa.Column("locale", sa.String(), nullable=False, comment="语言标签（BCP-47）"),
        sa.Column("fallback_order", JSONType, nullable=False, comment="回退顺序（数组），如 ['zh-Hans','zh']"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("project_id", "locale", name="pk_locales_fallbacks"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_table("th_locales_fallbacks")
    op.drop_table("th_tm_links")
    op.drop_index("ix_tm_last_used", table_name="th_tm")
    op.drop_table("th_tm")

    if dialect == "postgresql":
        try:
            op.drop_index("uq_translations_published", table_name="th_translations")
        except Exception:
            pass
        op.execute("DROP TRIGGER IF EXISTS trg_trans_derive_project_ins ON th_translations;")
        op.execute("DROP TRIGGER IF EXISTS trg_trans_derive_project_upd ON th_translations;")
        op.execute("DROP TRIGGER IF EXISTS trg_trans_touch_updated_at ON th_translations;")
    else:
        op.execute("DROP INDEX IF EXISTS uq_translations_published;")

    op.drop_index("ix_trans_project_lang_status", table_name="th_translations")
    op.drop_index("ix_trans_lang_status", table_name="th_translations")
    op.drop_index("ix_trans_content_lang", table_name="th_translations")
    op.drop_table("th_translations")

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_content_forbid_uida_update ON th_content;")
        op.execute("DROP TRIGGER IF EXISTS trg_content_touch_updated_at ON th_content;")
        op.execute("DROP FUNCTION IF EXISTS th_content_forbid_uida_update();")
        op.execute("DROP FUNCTION IF EXISTS set_updated_at();")

    op.drop_index("ix_content_project_namespace_version", table_name="th_content")
    op.drop_index("ix_content_project_namespace", table_name="th_content")
    op.drop_table("th_content")

    translation_status = sa.Enum(
        "draft", "reviewed", "published", "rejected", name="translation_status"
    )
    try:
        translation_status.drop(bind, checkfirst=True)
    except Exception:
        pass