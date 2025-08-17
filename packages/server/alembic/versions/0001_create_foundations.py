# packages/server/alembic/versions/0001_create_foundations.py
"""
迁移 0001: 奠定基础

职责:
- 创建 'th' schema。
- 启用 'pg_trgm' 扩展。
- 定义 'th.translation_status' ENUM 自定义类型。
- 创建所有核心 SQL 函数，为后续的表定义和触发器提供支持。

Revision ID: 0001
Revises: 
Create Date: 2025-08-17 16:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

# 将 SQL 逻辑封装在字符串中，保持 Alembic 脚本的清晰性
SQL_UP = """
-- 奠定基础：Schema, 扩展, 类型
CREATE SCHEMA IF NOT EXISTS th;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'translation_status' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'th')) THEN
        CREATE TYPE th.translation_status AS ENUM ('draft', 'reviewed', 'published', 'rejected');
    END IF;
END $$;

-- 核心函数
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
    RAISE EXCEPTION 'UIDA fields (project_id, namespace, keys_sha256_bytes) are immutable.';
  END IF;
  RETURN NEW;
END;
$$;
"""

SQL_DOWN = """
-- 逆序清理基础对象
DROP FUNCTION IF EXISTS th.forbid_uida_update() CASCADE;
DROP FUNCTION IF EXISTS th.extract_text(JSONB) CASCADE;
DROP FUNCTION IF EXISTS th.set_updated_at() CASCADE;
DROP FUNCTION IF EXISTS th.variant_normalize() CASCADE;
DROP FUNCTION IF EXISTS th.is_bcp47(TEXT) CASCADE;
DROP TYPE IF EXISTS th.translation_status CASCADE;
DROP EXTENSION IF EXISTS pg_trgm;
-- 不删除 schema 以保护 alembic_version 表
"""

def upgrade() -> None:
    """应用此迁移。"""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(SQL_UP)

def downgrade() -> None:
    """回滚此迁移。"""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(SQL_DOWN)