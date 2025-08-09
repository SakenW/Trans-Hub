# alembic/versions/3f8b9e6a0c2c_initial_schema.py
"""
TRANS-HUB 数据库初始架构（UIDA 最优版 · v1.0）

Revision ID: 3f8b9e6a0c2c
Revises:
Create Date: 2024-05-22 11:30:00.000000

本迁移脚本完全实现“权威指南”中的核心表与约束：
- 源/译分离：th_content（源内容权威）、th_translations（按语言/变体的权威译文）
- 复用与追溯：th_tm（翻译记忆库）、th_tm_links（复用追溯）
- 语言回退：th_locales_fallbacks
- 治理与事件（建议但纳入）：th_translation_reviews、th_translation_events
- 可靠外发：th_outbox
- 关键约束：UIDA 唯一、译文“唯一发布”的部分唯一索引（WHERE status='published'）
- 附加：PostgreSQL 下为 UIDA 三元添加不可变触发器与函数

兼容 SQLite 与 PostgreSQL；对方言特性（部分唯一索引、触发器）做了条件分支。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3f8b9e6a0c2c"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    升级步骤说明（按依赖顺序创建）：
    1) 基础枚举/类型（如需要）
    2) th_content（源内容权威，UIDA 唯一）
    3) th_tm（翻译记忆库）
    4) th_translations（译文权威，FK→content，可选 FK→tm）
    5) th_tm_links（复用追溯，FK→translations/tm）
    6) th_locales_fallbacks（语言回退策略）
    7) th_translation_reviews / th_translation_events（治理/审计）
    8) th_outbox（可靠外发）
    9) 方言特性（部分唯一索引、触发器函数）
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # -------------------------------------------------------------------------
    # 1) 定义通用枚举/约束（尽量用通用做法，保持 SQLite/PG 兼容）
    # -------------------------------------------------------------------------
    # 译文状态：draft|reviewed|published|rejected
    translation_status = sa.Enum(
        "draft", "reviewed", "published", "rejected", name="translation_status"
    )
    translation_status.create(bind, checkfirst=True)

    # -------------------------------------------------------------------------
    # 2) th_content：源内容权威（UIDA 唯一）
    #    UIDA = (project_id, namespace, keys_sha256_bytes)
    # -------------------------------------------------------------------------
    op.create_table(
        "th_content",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False, comment="多项目/多租户隔离"),
        sa.Column("namespace", sa.String(), nullable=False, comment="内容类型（建议显式版本位，如 .v1）"),
        sa.Column(
            "keys_sha256_bytes",
            sa.LargeBinary(length=32),
            nullable=False,
            comment="JCS(keys) 的 SHA-256 原始 32 字节摘要",
        ),
        sa.Column(
            "keys_b64",
            sa.Text(),
            nullable=False,
            comment="JCS(keys) 的 Base64URL 文本（用于跨系统对齐与导出）",
        ),
        sa.Column(
            "keys_json_debug",
            sa.Text(),
            nullable=True,
            comment="JCS(keys) 的原始 JSON 文本（仅用于调试，可截断/压缩）",
        ),
        sa.Column(
            "source_payload_json",
            sa.JSON(),
            nullable=False,
            comment="原文及元数据（结构化 JSON）",
        ),
        sa.Column(
            "content_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="业务侧内容版本号（非 DB 修订）",
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="归档时间；为历史/下线内容打标",
        ),
        sa.Column(
            "content_type",
            sa.String(),
            nullable=True,
            comment="可选：text/image/audio/file 等",
        ),
        sa.Column(
            "snapshots_json",
            sa.JSON(),
            nullable=True,
            comment="【可选非权威缓存】常用语言的已发布译文快照 + 校验和 + 时间戳",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "namespace",
            "keys_sha256_bytes",
            name="uq_content_uida",
            deferrable=False,
            initially="IMMEDIATE",
        ),
    )
    # 常用查询索引
    op.create_index(
        "ix_content_project_namespace", "th_content", ["project_id", "namespace"], unique=False
    )
    op.create_index(
        "ix_content_project_namespace_version",
        "th_content",
        ["project_id", "namespace", "content_version"],
        unique=False,
    )

    # -------------------------------------------------------------------------
    # 3) th_tm：翻译记忆库（复用结果仓）
    #    唯一键包含策略/算法版本，允许策略演进并存
    # -------------------------------------------------------------------------
    op.create_table(
        "th_tm",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column(
            "reuse_sha256_bytes",
            sa.LargeBinary(length=32),
            nullable=False,
            comment="等价键：基于“降维 keys + 归一化源文本”的稳定摘要（原始 32 字节）",
        ),
        sa.Column(
            "source_text_json",
            sa.JSON(),
            nullable=False,
            comment="归一化后的源文本片段（含 text_norm、占位符/标签骨架等）",
        ),
        sa.Column(
            "translated_json",
            sa.JSON(),
            nullable=False,
            comment="复用的译文结果（结构化 JSON）",
        ),
        sa.Column(
            "variant_key",
            sa.String(),
            nullable=False,
            server_default=sa.text("'-'"),
            comment="语言内变体（如 num/gender/formality/script/register 的固定序编码）",
        ),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column(
            "visibility_scope",
            sa.String(),
            nullable=False,
            server_default=sa.text("'project'"),
            comment="复用可见域：project|tenant|global",
        ),
        sa.Column(
            "pii_flags",
            sa.JSON(),
            nullable=True,
            comment="敏感/隐私标记（如包含姓名/邮箱等）",
        ),
        sa.Column(
            "policy_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="复用策略版本号",
        ),
        sa.Column(
            "hash_algo_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="哈希/归一化算法版本号",
        ),
        sa.Column(
            "reuse_policy_fingerprint",
            sa.String(),
            nullable=True,
            comment="策略指纹（用于唯一键维度精确对齐）",
        ),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
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
    )
    op.create_index("ix_tm_last_used", "th_tm", ["last_used_at"], unique=False)

    # -------------------------------------------------------------------------
    # 4) th_translations：按语言/变体的权威译文
    #    关键：同维度仅允许一条“published”（部分唯一索引）
    # -------------------------------------------------------------------------
    op.create_table(
        "th_translations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False, comment="冗余加速与 RLS"),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("source_lang", sa.String(), nullable=True),
        sa.Column("target_lang", sa.String(), nullable=False, comment="BCP-47"),
        sa.Column(
            "variant_key",
            sa.String(),
            nullable=False,
            server_default=sa.text("'-'"),
            comment="语言内变体编码；无变体固定为 '-'",
        ),
        sa.Column("status", sa.Enum(name="translation_status"), nullable=False),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="语言内修订号：编辑译文时 +1，状态切换不增加",
        ),
        sa.Column(
            "translated_payload_json",
            sa.JSON(),
            nullable=True,
            comment="结构化译文及元数据",
        ),
        sa.Column(
            "tm_id",
            sa.String(),
            nullable=True,
            comment="若命中 TM，则记录来源 TM 记录的 id",
        ),
        sa.Column("origin_lang", sa.String(), nullable=True, comment="回退来源语言"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("lint_report_json", sa.JSON(), nullable=True),
        sa.Column("engine_name", sa.String(), nullable=True),
        sa.Column("engine_version", sa.String(), nullable=True),
        sa.Column("prompt_hash", sa.String(), nullable=True),
        sa.Column("params_hash", sa.String(), nullable=True),
        sa.Column("last_reviewed_by", sa.String(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_revision", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["content_id"], ["th_content.id"], ondelete="CASCADE", name="fk_trans_content"
        ),
        # 注意：tm_id 可能为空；不启用 FK 以避免循环依赖，
        # 也可以启用 FK→th_tm.id（无循环），此处开启以确保一致性：
        sa.ForeignKeyConstraint(["tm_id"], ["th_tm.id"], name="fk_trans_tm", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "content_id",
            "target_lang",
            "variant_key",
            "revision",
            name="uq_translations_revision",
        ),
    )
    # 常用检索索引
    op.create_index(
        "ix_trans_content_lang", "th_translations", ["content_id", "target_lang"], unique=False
    )
    op.create_index(
        "ix_trans_lang_status", "th_translations", ["target_lang", "status"], unique=False
    )
    op.create_index(
        "ix_trans_project_lang_status",
        "th_translations",
        ["project_id", "target_lang", "status"],
        unique=False,
    )
    op.create_index("ix_trans_tm", "th_translations", ["tm_id"], unique=False)

    # “唯一发布”部分唯一索引：同(content_id,target_lang,variant_key) 仅允许一条 status='published'
    if dialect == "postgresql":
        op.create_index(
            "uq_translations_published",
            "th_translations",
            ["content_id", "target_lang", "variant_key"],
            unique=True,
            postgresql_where=sa.text("status = 'published'"),
        )
    else:
        # SQLite 等方言：显式执行局部唯一索引（SQLite 亦支持 partial index）
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_translations_published "
            "ON th_translations(content_id, target_lang, variant_key) "
            "WHERE status = 'published';"
        )

    # -------------------------------------------------------------------------
    # 5) th_tm_links：复用追溯（多对多：译文 ↔ TM）
    # -------------------------------------------------------------------------
    op.create_table(
        "th_tm_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("translation_id", sa.String(), nullable=False),
        sa.Column("tm_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["translation_id"],
            ["th_translations.id"],
            ondelete="CASCADE",
            name="fk_tm_links_translation",
        ),
        sa.ForeignKeyConstraint(["tm_id"], ["th_tm.id"], ondelete="CASCADE", name="fk_tm_links_tm"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("translation_id", "tm_id", name="uq_tm_links_pair"),
    )

    # -------------------------------------------------------------------------
    # 6) th_locales_fallbacks：语言回退策略（项目级）
    # -------------------------------------------------------------------------
    op.create_table(
        "th_locales_fallbacks",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column(
            "fallback_order",
            sa.JSON(),
            nullable=False,
            comment="回退顺序（数组/有序结构），如 ['zh-TW','zh-Hant','zh']",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("project_id", "locale", name="pk_locales_fallbacks"),
    )

    # -------------------------------------------------------------------------
    # 7) 治理与事件（建议但纳入）：审校与事件流水
    # -------------------------------------------------------------------------
    op.create_table(
        "th_translation_reviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("translation_id", sa.String(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False, comment="approve|reject|comment"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["translation_id"],
            ["th_translations.id"],
            ondelete="CASCADE",
            name="fk_reviews_translation",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reviews_project_translation",
        "th_translation_reviews",
        ["project_id", "translation_id"],
        unique=False,
    )

    op.create_table(
        "th_translation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False, comment="create/reuse/edit/publish/..."),
        sa.Column("entity_table", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_events_project_type", "th_translation_events", ["project_id", "event_type"], unique=False
    )
    op.create_index(
        "ix_events_entity", "th_translation_events", ["entity_table", "entity_id"], unique=False
    )

    # -------------------------------------------------------------------------
    # 8) th_outbox：可靠外发（Outbox 模式）
    # -------------------------------------------------------------------------
    op.create_table(
        "th_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False, comment="幂等键"),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="pending|delivered|failed|dead",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="投递重试计数",
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_status", "th_outbox", ["status"], unique=False)
    op.create_index(
        "ix_outbox_project_status",
        "th_outbox",
        ["project_id", "status", "created_at"],
        unique=False,
    )
    op.create_index("ux_outbox_event_id", "th_outbox", ["event_id"], unique=True)

    # -------------------------------------------------------------------------
    # 9) PostgreSQL 专属：UIDA 不可变守卫（防止误更新）
    # -------------------------------------------------------------------------
    if dialect == "postgresql":
        # 创建一个触发器函数：阻止对 UIDA 三元（project_id, namespace, keys_sha256_bytes）的更新
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


def downgrade() -> None:
    """
    降级顺序：先删依赖（索引/触发器/表），再删基础类型。
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    # PostgreSQL：删除 UIDA 不可变触发器与函数
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_content_forbid_uida_update ON th_content;")
        op.execute("DROP FUNCTION IF EXISTS th_content_forbid_uida_update();")

    # th_outbox
    op.drop_index("ux_outbox_event_id", table_name="th_outbox")
    op.drop_index("ix_outbox_project_status", table_name="th_outbox")
    op.drop_index("ix_outbox_status", table_name="th_outbox")
    op.drop_table("th_outbox")

    # th_translation_events
    op.drop_index("ix_events_entity", table_name="th_translation_events")
    op.drop_index("ix_events_project_type", table_name="th_translation_events")
    op.drop_table("th_translation_events")

    # th_translation_reviews
    op.drop_index("ix_reviews_project_translation", table_name="th_translation_reviews")
    op.drop_table("th_translation_reviews")

    # th_locales_fallbacks
    op.drop_table("th_locales_fallbacks")

    # th_tm_links
    op.drop_table("th_tm_links")

    # th_translations（先删索引）
    if dialect == "postgresql":
        op.drop_index("uq_translations_published", table_name="th_translations")
    else:
        op.execute(
            "DROP INDEX IF EXISTS uq_translations_published;"
        )
    op.drop_index("ix_trans_tm", table_name="th_translations")
    op.drop_index("ix_trans_project_lang_status", table_name="th_translations")
    op.drop_index("ix_trans_lang_status", table_name="th_translations")
    op.drop_index("ix_trans_content_lang", table_name="th_translations")
    op.drop_table("th_translations")

    # th_tm
    op.drop_index("ix_tm_last_used", table_name="th_tm")
    op.drop_table("th_tm")

    # th_content
    op.drop_index("ix_content_project_namespace_version", table_name="th_content")
    op.drop_index("ix_content_project_namespace", table_name="th_content")
    op.drop_table("th_content")

    # 基础枚举类型
    translation_status = sa.Enum(
        "draft", "reviewed", "published", "rejected", name="translation_status"
    )
    translation_status.drop(bind, checkfirst=True)
