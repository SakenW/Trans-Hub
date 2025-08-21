# packages/server/tests/conftest.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# --- 导入路径修复 ---
TESTS_DIR = Path(__file__).parent
SERVER_DIR = TESTS_DIR.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# --- 业务侧依赖 ---
from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config, create_coordinator
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import create_async_sessionmaker, dispose_engine
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork, UowFactory

from tests.helpers.tools.db_manager import managed_temp_database


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def test_config() -> TransHubConfig:
    return create_app_config(env_mode="test")


@pytest_asyncio.fixture
async def migrated_db(test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    临时数据库 + ORM create_all，并逐条安装：
      - RLS 函数/策略（测试友好：未设置 GUC 时放开；空字符串时拒绝）
      - 触发器（全部 BEFORE）：
         * 变体键规范化
         * 发布/撤回：写事件(含 payload)、维护 published_at、精准清缓存
         * 任意 UPDATE 刷新 updated_at
    说明：为兼容 asyncpg，所有顶层 DDL 均按“单语句”拆分执行。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip("维护库 DSN 未配置，跳过数据库相关测试")

    maint_url = make_url(raw_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        async_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+psycopg", "+asyncpg"
        )
        eng = create_async_engine(async_dsn)

        async with eng.begin() as conn:
            # 1) schema + ORM 表
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
            await conn.run_sync(Base.metadata.create_all)

            # 2) RLS（测试友好）
            await conn.execute(
                text(
                    r"""
CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
DECLARE v TEXT := current_setting('th.allowed_projects', true);
BEGIN
  IF v IS NULL THEN
    RETURN NULL; -- 未设置 => 放开（测试）
  END IF;
  IF btrim(v) = '' THEN
    RETURN ARRAY[]::TEXT[]; -- 空串 => 拒绝
  END IF;
  RETURN string_to_array(regexp_replace(v, '\s+', '', 'g'), ',');
END;
$$;
"""
                )
            )

            await conn.execute(
                text(
                    r"""
DO $$
DECLARE
  tables_with_rls TEXT[] := ARRAY[
    'projects','content','trans_rev','trans_head','resolve_cache',
    'events','comments','locales_fallbacks','tm_units','tm_links'
  ];
  t_name TEXT;
BEGIN
  FOREACH t_name IN ARRAY tables_with_rls LOOP
    EXECUTE format('ALTER TABLE th.%I ENABLE ROW LEVEL SECURITY;', t_name);
    EXECUTE format('ALTER TABLE th.%I FORCE ROW LEVEL SECURITY;', t_name);
    EXECUTE format('DROP POLICY IF EXISTS p_%1$s_rls ON th.%1$s;', t_name);
    EXECUTE format(
      'CREATE POLICY p_%1$s_rls ON th.%1$s FOR ALL TO PUBLIC ' ||
      'USING (th.allowed_projects() IS NULL OR project_id = ANY(th.allowed_projects())) ' ||
      'WITH CHECK (th.allowed_projects() IS NULL OR project_id = ANY(th.allowed_projects()));',
      t_name
    );
  END LOOP;
END $$;
"""
                )
            )

            # 3) 触发器

            # 3a) 变体规范化函数
            await conn.execute(
                text(
                    r"""
CREATE OR REPLACE FUNCTION th.fn_normalize_variant_key(p_input VARCHAR)
RETURNS VARCHAR
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v TEXT;
BEGIN
  IF p_input IS NULL THEN
    RETURN '-';
  END IF;
  v := btrim(p_input);
  IF v = '' THEN
    RETURN '-';
  END IF;
  v := lower(v);
  v := regexp_replace(v, '\s+', '-', 'g');
  RETURN v;
END;
$$;
"""
                )
            )

            # 3b) BEFORE：trans_head.variant_key 规范化
            await conn.execute(
                text(
                    r"""
CREATE OR REPLACE FUNCTION th.trg_biu_trans_head_normalize_variant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.variant_key := th.fn_normalize_variant_key(NEW.variant_key);
  RETURN NEW;
END;
$$;
"""
                )
            )
            await conn.execute(
                text(
                    "DROP TRIGGER IF EXISTS biu_trans_head_normalize_variant ON th.trans_head;"
                )
            )
            await conn.execute(
                text(
                    r"""
CREATE TRIGGER biu_trans_head_normalize_variant
BEFORE INSERT OR UPDATE OF variant_key ON th.trans_head
FOR EACH ROW
EXECUTE FUNCTION th.trg_biu_trans_head_normalize_variant();
"""
                )
            )

            # 3c) BEFORE：发布/撤回（写事件含 payload）
            await conn.execute(
                text(
                    r"""
CREATE OR REPLACE FUNCTION th.trg_bu_trans_head_publish()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.published_rev_id IS DISTINCT FROM OLD.published_rev_id) THEN
    IF NEW.published_rev_id IS NOT NULL THEN
      -- 发布
      NEW.published_no := NULL;
      NEW.published_at := now();

      INSERT INTO th.events (project_id, head_id, actor, event_type, payload)
      VALUES (
        NEW.project_id,
        NEW.id,
        'system',
        'published',
        jsonb_build_object(
          'new_rev', NEW.published_rev_id,
          'old_rev', OLD.published_rev_id
        )
      );
    ELSE
      -- 撤回发布
      NEW.published_no := NULL;
      NEW.published_at := NULL;

      INSERT INTO th.events (project_id, head_id, actor, event_type, payload)
      VALUES (
        NEW.project_id,
        NEW.id,
        'system',
        'unpublished',
        jsonb_build_object(
          'old_rev', OLD.published_rev_id
        )
      );
    END IF;

    -- 精准失效缓存（同 content + 语言 + 变体）
    DELETE FROM th.resolve_cache
     WHERE project_id = NEW.project_id
       AND content_id  = NEW.content_id
       AND target_lang = NEW.target_lang
       AND variant_key = NEW.variant_key;
  END IF;

  RETURN NEW;
END;
$$;
"""
                )
            )
            await conn.execute(
                text("DROP TRIGGER IF EXISTS bu_trans_head_publish ON th.trans_head;")
            )
            await conn.execute(
                text(
                    r"""
CREATE TRIGGER bu_trans_head_publish
BEFORE UPDATE OF published_rev_id ON th.trans_head
FOR EACH ROW
EXECUTE FUNCTION th.trg_bu_trans_head_publish();
"""
                )
            )

            # 3d) BEFORE：任意 UPDATE 刷新 updated_at
            await conn.execute(
                text(
                    r"""
CREATE OR REPLACE FUNCTION th.trg_bu_trans_head_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;
"""
                )
            )
            await conn.execute(
                text(
                    "DROP TRIGGER IF EXISTS bu_trans_head_set_updated_at ON th.trans_head;"
                )
            )
            await conn.execute(
                text(
                    r"""
CREATE TRIGGER bu_trans_head_set_updated_at
BEFORE UPDATE ON th.trans_head
FOR EACH ROW
EXECUTE FUNCTION th.trg_bu_trans_head_set_updated_at();
"""
                )
            )

            # 4) GRANT
            await conn.execute(
                text("GRANT EXECUTE ON FUNCTION th.allowed_projects() TO PUBLIC;")
            )
            await conn.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION th.fn_normalize_variant_key(VARCHAR) TO PUBLIC;"
                )
            )
            await conn.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION th.trg_biu_trans_head_normalize_variant() TO PUBLIC;"
                )
            )
            await conn.execute(
                text(
                    "GRANT EXECUTE ON FUNCTION th.trg_bu_trans_head_publish() TO PUBLIC;"
                )
            )

            await conn.commit()

        try:
            yield eng
        finally:
            await dispose_engine(eng)


@pytest.fixture
def uow_factory(migrated_db: AsyncEngine) -> UowFactory:
    sessionmaker = create_async_sessionmaker(migrated_db)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig, migrated_db: AsyncEngine
) -> AsyncGenerator[Coordinator, None]:
    local_config = test_config.model_copy(deep=True)
    local_config.database.url = migrated_db.url.render_as_string(hide_password=False)
    coord, db_engine_from_bootstrap = await create_coordinator(local_config)
    try:
        yield coord
    finally:
        await coord.close()
        await dispose_engine(db_engine_from_bootstrap)


@pytest_asyncio.fixture
async def rls_engine(
    migrated_db: AsyncEngine,
    test_config: TransHubConfig,
) -> AsyncGenerator[AsyncEngine, None]:
    """
    低权限用户引擎（用于 RLS 测试）：
      需要 TRANSHUB_TEST_USER_DATABASE__URL（以 / 结尾），测试夹具会拼接临时库名。
    """
    low_privilege_dsn_base = os.getenv("TRANSHUB_TEST_USER_DATABASE__URL")
    if not low_privilege_dsn_base:
        pytest.skip("缺少低权限用户 DSN，跳过 RLS 相关测试")

    db_name = migrated_db.url.database
    low_privilege_dsn = f"{low_privilege_dsn_base}{db_name}"

    # 授权
    async with migrated_db.begin() as conn:
        await conn.execute(
            text(f'GRANT CONNECT ON DATABASE "{db_name}" TO transhub_tester;')
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"
            )
        )
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA th "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO transhub_tester;"
            )
        )
        await conn.execute(
            text("GRANT EXECUTE ON FUNCTION th.allowed_projects() TO transhub_tester;")
        )
        await conn.execute(
            text(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA th TO transhub_tester;"
            )
        )
        await conn.commit()

    eng = create_async_engine(low_privilege_dsn)
    try:
        yield eng
    finally:
        await dispose_engine(eng)


@pytest.fixture
def uow_factory_rls(rls_engine: AsyncEngine) -> UowFactory:
    sessionmaker = create_async_sessionmaker(rls_engine)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)
