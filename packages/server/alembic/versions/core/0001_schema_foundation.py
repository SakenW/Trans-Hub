"""
L1-core-schema-0001_schema_foundation.py
职责：创建 schema/扩展、通用 ENUM、公共函数（不挂触发器）。
"""

from __future__ import annotations
from alembic import op

# Alembic identifiers
revision = "0001_schema_foundation"
down_revision = None
branch_labels = None
depends_on = None

SQL_UP = r"""
CREATE SCHEMA IF NOT EXISTS th;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ENUM 定义（幂等）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'translation_status' AND n.nspname = 'th'
  ) THEN
    CREATE TYPE th.translation_status AS ENUM ('draft','reviewed','published','rejected');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'event_severity' AND n.nspname = 'th'
  ) THEN
    CREATE TYPE th.event_severity AS ENUM ('info','warn','error');
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'workflow_state' AND n.nspname = 'th'
  ) THEN
    CREATE TYPE th.workflow_state AS ENUM ('draft','in_review','ready','frozen');
  END IF;
END$$;

-- BCP-47 校验
CREATE OR REPLACE FUNCTION th.is_bcp47(p TEXT)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT p IS NOT NULL AND p ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'
$$;

-- 变体标准化
CREATE OR REPLACE FUNCTION th.variant_normalize()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.variant_key IS NULL OR btrim(NEW.variant_key) = '' THEN
    NEW.variant_key := '-';
  ELSE
    NEW.variant_key := lower(NEW.variant_key);
  END IF;
  RETURN NEW;
END;
$$;

-- 自动 updated_at
CREATE OR REPLACE FUNCTION th.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- 稳定顺序的 JSONB 文本提取
CREATE OR REPLACE FUNCTION th.extract_text(j JSONB)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
  SELECT string_agg(value, ' ' ORDER BY key)
  FROM (
    SELECT key, value
    FROM jsonb_each_text(coalesce(j, '{}'::jsonb))
  ) t
$$;

-- 禁止 UIDA 修改
CREATE OR REPLACE FUNCTION th.forbid_uida_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'content.id (UIDA) is immutable';
  END IF;
  RETURN NEW;
END;
$$;

-- BCP-47 → tsvector 配置映射
CREATE OR REPLACE FUNCTION th.tsv_config_for_bcp47(lang TEXT)
RETURNS regconfig LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  base TEXT := lower(split_part(coalesce(lang, ''), '-', 1));
BEGIN
  RETURN CASE base
    WHEN 'en' THEN 'english'::regconfig
    WHEN 'de' THEN 'german'::regconfig
    WHEN 'fr' THEN 'french'::regconfig
    WHEN 'es' THEN 'spanish'::regconfig
    WHEN 'it' THEN 'italian'::regconfig
    WHEN 'ru' THEN 'russian'::regconfig
    WHEN 'pt' THEN 'portuguese'::regconfig
    ELSE 'simple'::regconfig
  END;
END;
$$;
"""

SQL_DOWN = r"""
DROP FUNCTION IF EXISTS th.tsv_config_for_bcp47(TEXT) CASCADE;
DROP FUNCTION IF EXISTS th.forbid_uida_update() CASCADE;
DROP FUNCTION IF EXISTS th.extract_text(JSONB) CASCADE;
DROP FUNCTION IF EXISTS th.set_updated_at() CASCADE;
DROP FUNCTION IF EXISTS th.variant_normalize() CASCADE;
DROP FUNCTION IF EXISTS th.is_bcp47(TEXT) CASCADE;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='workflow_state' AND n.nspname='th') THEN
    DROP TYPE th.workflow_state;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='event_severity' AND n.nspname='th') THEN
    DROP TYPE th.event_severity;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE t.typname='translation_status' AND n.nspname='th') THEN
    DROP TYPE th.translation_status;
  END IF;
END$$;

-- 按需决定是否删除扩展（通常不删）
-- DROP EXTENSION IF EXISTS pgcrypto;
-- DROP EXTENSION IF EXISTS pg_trgm;
"""


def upgrade() -> None:
    op.execute(SQL_UP)


def downgrade() -> None:
    op.execute(SQL_DOWN)
