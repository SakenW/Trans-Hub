"""
0001_schema_foundation.py (方言感知版)
职责：创建 schema/扩展、通用 ENUM、公共函数（不挂触发器）。
对齐基线：MIGRATION_GUIDE §L1 / 白皮书 v3.0 §6.*
"""

from __future__ import annotations

from alembic import op

# Alembic identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# --- PostgreSQL 特定 DDL ---

SQL_UP_COMMANDS = [
    "DROP SCHEMA IF EXISTS th CASCADE",
    "CREATE SCHEMA IF NOT EXISTS th",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    # 确保alembic_version表在th schema中创建
    r"""
CREATE TABLE IF NOT EXISTS th.alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
""",
    r"""
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
""",
    "DROP FUNCTION IF EXISTS th.is_bcp47(TEXT) CASCADE",
    r"""
CREATE OR REPLACE FUNCTION th.is_bcp47(p TEXT)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT p IS NOT NULL AND p ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$'
$$;
""",
    r"""
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
""",
    r"""
CREATE OR REPLACE FUNCTION th.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;
""",
    r"""
CREATE OR REPLACE FUNCTION th.extract_text(j JSONB)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
  SELECT string_agg(value, ' ' ORDER BY key)
  FROM (
    SELECT key, value
    FROM jsonb_each_text(coalesce(j, '{}'::jsonb))
  ) t
$$;
""",
    r"""
CREATE OR REPLACE FUNCTION th.forbid_uida_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'content.id (UIDA) is immutable';
  END IF;
  RETURN NEW;
END;
$$;
""",
    r"""
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
""",
]

SQL_DOWN_COMMANDS = [
    "DROP FUNCTION IF EXISTS th.tsv_config_for_bcp47(TEXT) CASCADE",
    "DROP FUNCTION IF EXISTS th.forbid_uida_update() CASCADE",
    "DROP FUNCTION IF EXISTS th.extract_text(JSONB) CASCADE",
    "DROP FUNCTION IF EXISTS th.set_updated_at() CASCADE",
    "DROP FUNCTION IF EXISTS th.variant_normalize() CASCADE",
    "DROP FUNCTION IF EXISTS th.is_bcp47(TEXT) CASCADE",
    r"""
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
""",
    # "-- 按需决定是否删除扩展（通常不删）",
    # "DROP EXTENSION IF EXISTS pgcrypto",
    # "DROP EXTENSION IF EXISTS pg_trgm",
    # "DROP SCHEMA IF EXISTS th",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for command in SQL_UP_COMMANDS:
            op.execute(command)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for command in SQL_DOWN_COMMANDS:
            op.execute(command)
