# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v6.2 · RLS 修复版)

核心优化:
- [战术性修复] 在 migrated_db 夹具中，于 `create_all` 之后手动应用了 RLS 策略
  相关的 DDL。这确保了 RLS 测试能在基于 ORM 创建的数据库上正确运行。
  该 DDL 逻辑源自 `alembic/versions/policy/0007_rls_policies.py`，
  未来若 RLS 策略变更，需手动同步此处。
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


# 导入路径修复
TESTS_DIR = Path(__file__).parent
SERVER_DIR = TESTS_DIR.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from tests.helpers.tools.db_manager import managed_temp_database
from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config, create_coordinator
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.db import create_async_sessionmaker, dispose_engine
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork, UowFactory


# --- 核心夹具 ---

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """强制 pytest-asyncio 使用 asyncio 后端。"""
    return "asyncio"


@pytest.fixture(scope="session")
def test_config() -> TransHubConfig:
    """提供一个会话级的、加载自 .env.test 的配置对象。"""
    return create_app_config(env_mode="test")


@pytest_asyncio.fixture
async def migrated_db(test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    提供一个引擎，它连接到一个全新的、已通过 ORM `create_all` 初始化
    并手动应用了 RLS 策略的临时数据库。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip("维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置")

    maint_url = make_url(raw_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        async_dsn = temp_db_url.render_as_string(hide_password=False).replace("+psycopg", "+asyncpg")
        
        eng = create_async_engine(async_dsn)

        async with eng.begin() as conn:
            # 1. 创建 Schema 和 ORM 定义的表
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
            await conn.run_sync(Base.metadata.create_all)

            # 2. [战术性修复] 手动应用 RLS DDL
            # 该 DDL 逻辑源自 alembic/versions/policy/0007_rls_policies.py，
            # 因为 create_all 不会创建函数和 RLS 策略。
            # 未来若 RLS 策略变更，需手动同步此处。
            
            # 2a) 会话 GUC 解析函数
            await conn.execute(text(r"""
            CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
            DECLARE v TEXT := current_setting('th.allowed_projects', true);
            BEGIN
              IF v IS NULL OR btrim(v) = '' THEN
                RETURN ARRAY[]::TEXT[]; -- 默认拒绝
              END IF;
              RETURN string_to_array(regexp_replace(v, '\s+', '', 'g'), ',');
            END;
            $$;
            """))

            # 2b) 对所有业务表启用 RLS 并应用统一策略
            await conn.execute(text(r"""
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
                  'USING (project_id = ANY(th.allowed_projects())) ' ||
                  'WITH CHECK (project_id = ANY(th.allowed_projects()));',
                  t_name
                );
              END LOOP;
            END $$;
            """))

            await conn.commit()

        yield eng
        
        await dispose_engine(eng)


@pytest.fixture
def uow_factory(migrated_db: AsyncEngine) -> UowFactory:
    """提供一个直接连接到隔离临时数据库的 UoW 工厂。"""
    sessionmaker = create_async_sessionmaker(migrated_db)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,
) -> AsyncGenerator[Coordinator, None]:
    """提供一个连接到隔离临时数据库的 Coordinator 实例。"""
    local_config = test_config.model_copy(deep=True)
    local_config.database.url = migrated_db.url.render_as_string(hide_password=False)
    coord, db_engine_from_bootstrap = await create_coordinator(local_config)
    yield coord
    await coord.close()
    await dispose_engine(db_engine_from_bootstrap)


@pytest_asyncio.fixture
async def rls_engine(
    migrated_db: AsyncEngine,
    test_config: TransHubConfig,
) -> AsyncGenerator[AsyncEngine, None]:
    """提供一个使用【低权限】测试用户连接到已迁移数据库的引擎。"""
    low_privilege_dsn_base = os.getenv("TRANSHUB_TEST_USER_DATABASE__URL")
    if not low_privilege_dsn_base:
        pytest.skip("缺少低权限用户 DSN (TRANSHUB_TEST_USER_DATABASE__URL)，跳过 RLS 测试")

    db_name = migrated_db.url.database
    low_privilege_dsn = f"{low_privilege_dsn_base}{db_name}"

    async with migrated_db.begin() as conn:
        await conn.execute(text(f"GRANT CONNECT ON DATABASE \"{db_name}\" TO transhub_tester;"))
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"))
        await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA th GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO transhub_tester;"))
        # 额外授权，允许低权限用户调用 RLS 函数
        await conn.execute(text("GRANT EXECUTE ON FUNCTION th.allowed_projects() TO transhub_tester;"))


    eng = create_async_engine(low_privilege_dsn)
    yield eng
    await dispose_engine(eng)


@pytest.fixture
def uow_factory_rls(
    rls_engine: AsyncEngine,
) -> UowFactory:
    """提供一个使用【低权限】引擎的 UoW 工厂，专用于 RLS 测试。"""
    sessionmaker = create_async_sessionmaker(rls_engine)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)
