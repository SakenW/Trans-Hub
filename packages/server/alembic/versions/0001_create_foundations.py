# packages/server/alembic/versions/0001_create_foundations.py
"""
迁移 0001: 奠定基础（最终替换版）
- 创建 schema/扩展/ENUM
- 定义核心函数: is_bcp47, variant_normalize, set_updated_at, forbid_uida_update
"""
from __future__ import annotations
from alembic import op

# Alembic identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_UP = r"""
-- 1) 基础对象
CREATE SCHEMA IF NOT EXISTS th;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'translation_status' AND n.nspname = 'th'
  ) THEN
    CREATE TYPE th.translation_status AS ENUM ('draft','reviewed','published','rejected');
  END IF;
END$$;

-- 2) 通用校验函数：是否为 BCP-47（宽松版）
CREATE OR REPLACE FUNCTION th.is_bcp47(p TEXT)
RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT p IS NOT NULL AND p ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'
$$;

-- 3) 触发器函数：标准化 variant_key（空/空白→'-'，其它转小写）
CREATE OR REPLACE FUNCTION th.variant_normalize()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.variant_key IS NULL OR btrim(NEW.variant_key) = '' THEN
    NEW.variant_key := '-';
  ELSE
    NEW.variant_key := lower(NEW.variant_key);
  END IF;
  RETURN NEW;
END;
$$;

-- 4) 触发器函数：自动维护 updated_at = now()
CREATE OR REPLACE FUNCTION th.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- 5) 触发器函数：禁止 content.id（UIDA）被修改
CREATE OR REPLACE FUNCTION th.forbid_uida_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'content.id (UIDA) is immutable';
  END IF;
  RETURN NEW;
END;
$$;
"""

SQL_DOWN = r"""
DROP FUNCTION IF EXISTS th.forbid_uida_update() CASCADE;
DROP FUNCTION IF EXISTS th.set_updated_at() CASCADE;
DROP FUNCTION IF EXISTS th.variant_normalize() CASCADE;
DROP FUNCTION IF EXISTS th.is_bcp47(TEXT) CASCADE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'translation_status' AND n.nspname = 'th'
  ) THEN
    DROP TYPE th.translation_status;
  END IF;
END$$;

-- 不删除 schema 以保护 alembic_version
DROP EXTENSION IF EXISTS pg_trgm;
"""

def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(SQL_UP)

def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(SQL_DOWN)
