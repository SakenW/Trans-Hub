# packages/server/alembic/versions/0002_create_core_tables.py
"""
迁移 0002: 构建核心表

职责:
- 创建系统的核心骨架表：
  - th.projects
  - th.content
  - th.trans_rev (分区父表)
  - th.trans_head (分区父表)

Revision ID: 0002
Revises: 0001
Create Date: 2025-08-17 16:01:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

# [最终修复] 定义 ENUM 类型，并明确设置 create_type=False
# 这告诉 SQLAlchemy：“在创建使用此类型的表时，不要尝试自动创建这个 ENUM 类型，
# 因为我们已经在 0001 迁移中手动管理了它。”
translation_status_enum = postgresql.ENUM(
    'draft', 'reviewed', 'published', 'rejected', 
    name='translation_status', schema='th', create_type=False
)

def upgrade() -> None:
    """应用此迁移。"""
    # === th.projects 表 ===
    op.create_table(
        'projects',
        sa.Column('project_id', sa.Text(), nullable=False, comment='多租户边界，项目唯一 ID'),
        sa.Column('display_name', sa.Text(), nullable=False, comment='展示名'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False, comment='是否启用'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（UTC）'),
        sa.PrimaryKeyConstraint('project_id'),
        schema='th'
    )

    # === th.content 表 ===
    op.create_table(
        'content',
        sa.Column('id', sa.Text(), nullable=False, comment='内容键实体化（UIDA 的 ID）'),
        sa.Column('project_id', sa.Text(), nullable=False, comment='所属项目'),
        sa.Column('namespace', sa.Text(), nullable=False, comment='内容命名空间'),
        sa.Column('keys_sha256_bytes', sa.LargeBinary(length=32), nullable=False, comment='Canonical JSON→SHA-256 结果'),
        sa.Column('source_lang', sa.Text(), nullable=False, comment='源语言'),
        sa.Column('source_payload_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False, comment='源内容载荷'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='创建时间（UTC）'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='更新时间（UTC）'),
        sa.ForeignKeyConstraint(['project_id'], ['th.projects.project_id'], deferrable=True, initially='DEFERRED'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'namespace', 'keys_sha256_bytes', name='uq_content_uida'),
        sa.CheckConstraint('octet_length(keys_sha256_bytes) = 32', name='ck_content_sha256_len'),
        sa.CheckConstraint('th.is_bcp47(source_lang)', name='ck_content_source_lang_bcp47'),
        schema='th'
    )

    # === th.trans_rev 分区父表 ===
    op.create_table(
        'trans_rev',
        sa.Column('project_id', sa.Text(), nullable=False, comment='分区键/租户边界'),
        sa.Column('id', sa.Text(), nullable=False, comment='修订 ID（ULID/Snowflake）'),
        sa.Column('content_id', sa.Text(), nullable=False, comment='关联内容'),
        sa.Column('target_lang', sa.Text(), nullable=False, comment='目标语言'),
        sa.Column('variant_key', sa.Text(), server_default='-', nullable=False, comment='变体（平台/主题等）'),
        sa.Column('revision_no', sa.Integer(), nullable=False, comment='修订号，用于排序和冲突检测'),
        sa.Column('status', translation_status_enum, nullable=False, comment='修订状态'), # [关键修改]
        sa.Column('origin_lang', sa.Text(), nullable=True, comment="溯源语言 (如 'tm', 'en-US')"),
        sa.Column('src_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='翻译时的源内容快照'),
        sa.Column('translated_payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='托管的译文载荷'),
        sa.Column('engine_name', sa.Text(), nullable=True),
        sa.Column('engine_version', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['content_id'], ['th.content.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('project_id', 'id'),
        sa.UniqueConstraint('project_id', 'content_id', 'target_lang', 'variant_key', 'revision_no', name='uq_rev_dim'),
        sa.CheckConstraint('th.is_bcp47(target_lang)', name='ck_rev_target_lang_bcp47'),
        sa.CheckConstraint("origin_lang IS NULL OR th.is_bcp47(origin_lang)", name='ck_rev_origin_lang_bcp47'),
        schema='th',
        postgresql_partition_by='HASH (project_id)'
    )

    # === th.trans_head 分区父表 ===
    op.create_table(
        'trans_head',
        sa.Column('project_id', sa.Text(), nullable=False, comment='租户边界'),
        sa.Column('id', sa.Text(), nullable=False, comment='头指针 ID'),
        sa.Column('content_id', sa.Text(), nullable=False, comment='内容键'),
        sa.Column('target_lang', sa.Text(), nullable=False, comment='目标语言'),
        sa.Column('variant_key', sa.Text(), server_default='-', nullable=False, comment='变体'),
        sa.Column('current_rev_id', sa.Text(), nullable=False, comment='当前草稿/工作版本'),
        sa.Column('current_status', translation_status_enum, nullable=False, comment='当前修订状态（性能优化）'), # [关键修改]
        sa.Column('current_no', sa.Integer(), nullable=False, comment='当前修订号（性能优化）'),
        sa.Column('published_rev_id', sa.Text(), nullable=True, comment='已发布版本'),
        sa.Column('published_no', sa.Integer(), nullable=True, comment='已发布修订号'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True, comment='发布时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['content_id'], ['th.content.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id', 'current_rev_id'], ['th.trans_rev.project_id', 'th.trans_rev.id'], ondelete='RESTRICT', deferrable=True, initially='DEFERRED'),
        sa.ForeignKeyConstraint(['project_id', 'published_rev_id'], ['th.trans_rev.project_id', 'th.trans_rev.id'], ondelete='RESTRICT', deferrable=True, initially='DEFERRED'),
        sa.PrimaryKeyConstraint('project_id', 'id'),
        sa.UniqueConstraint('project_id', 'content_id', 'target_lang', 'variant_key', name='uq_head_dim'),
        sa.UniqueConstraint('project_id', 'published_rev_id', name='uq_head_published_rev'),
        sa.CheckConstraint('th.is_bcp47(target_lang)', name='ck_head_target_lang_bcp47'),
        schema='th',
        postgresql_partition_by='HASH (project_id)'
    )

def downgrade() -> None:
    """回滚此迁移。"""
    op.drop_table('trans_head', schema='th')
    op.drop_table('trans_rev', schema='th')
    op.drop_table('content', schema='th')
    op.drop_table('projects', schema='th')