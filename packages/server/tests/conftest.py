# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v7.0 · DI 重构版)

核心变更:
- `app_container` 成为核心夹具，负责创建和管理 DI 容器的生命周期。
- `coordinator` 和 `uow_factory` 等业务夹具现在直接从 `app_container` 中获取实例。
- `migrated_db` 夹具职责简化，仅负责创建和销毁临时数据库。
- 保留了独立的 `rls_engine` 和 `uow_factory_rls` 夹具，用于专门的 RLS 权限测试，
  确保测试的隔离性和目的性。
"""

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
if str(SERVER_DIR / "src") not in sys.path:
    sys.path.insert(0, str(SERVER_DIR / "src"))

# --- [DI 重构] 导入 DI 相关 ---
from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config, create_container
from trans_hub.config import TransHubConfig
from trans_hub.containers import ApplicationContainer
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.uow import UowFactory

from tests.helpers.tools.db_manager import managed_temp_database

# =========================
# 核心夹具
# =========================


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """强制 pytest-asyncio 使用 asyncio 后端。"""
    return "asyncio"


@pytest.fixture(scope="session")
def test_config() -> TransHubConfig:
    """提供一个会话级配置对象，加载 .env.test。"""
    return create_app_config(env_mode="test")


@pytest_asyncio.fixture
async def migrated_db(test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    提供一个临时的、Schema 已创建的数据库引擎。
    此夹具现在只负责数据库的创建、ORM 表结构的建立和销毁。
    注意：测试用的触发器和 RLS 策略现在在 e2e/integration 测试中按需应用，
    或通过一个更高级的夹具来添加。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip(
            "维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置，跳过数据库相关测试"
        )

    maint_url = make_url(raw_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        # 将 psycopg DSN 转换为 asyncpg DSN
        async_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+psycopg", "+asyncpg"
        )
        engine = create_async_engine(async_dsn)

        async with engine.begin() as conn:
            # 仅创建 ORM 定义的 Schema
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()


@pytest_asyncio.fixture
async def app_container(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,
) -> AsyncGenerator[ApplicationContainer, None]:
    """
    [DI 重构] 提供一个连接到隔离临时数据库的、完全初始化的 DI 容器。
    这是大多数集成测试应依赖的核心夹具。
    """
    local_config = test_config.model_copy(deep=True)
    real_db_url = migrated_db.url.render_as_string(hide_password=False)
    local_config.database.url = real_db_url

    container = create_container(local_config, service_name="pytest-runner")

    # 关键：使用 with 语句来覆盖 provider，用于测试
    with container.persistence.db_engine.override(migrated_db):
        # 初始化资源 (现在使用的是被覆盖的 migrated_db)
        await container.init_resources()
        yield container
        # 关闭资源
        await container.shutdown_resources()


@pytest.fixture
def coordinator(app_container: ApplicationContainer) -> Coordinator:
    """[DI 重构] 从测试容器中获取一个 Coordinator 实例。"""
    return app_container.services.coordinator()


@pytest.fixture
def uow_factory(app_container: ApplicationContainer) -> UowFactory:
    """[DI 重构] 从测试容器中获取 UoW 工厂。"""
    return app_container.persistence.uow_factory()


# =========================
# RLS 专用夹具 (保持独立)
# =========================


@pytest_asyncio.fixture
async def rls_engine(
    migrated_db: AsyncEngine,
    test_config: TransHubConfig,
) -> AsyncGenerator[AsyncEngine, None]:
    """
    提供一个使用【低权限】测试用户连接的引擎，用于 RLS 测试。
    此引擎连接的数据库已通过 migrated_db 夹具创建。
    """
    low_privilege_dsn_base = os.getenv("TRANSHUB_TEST_USER_DATABASE__URL")
    if not low_privilege_dsn_base:
        pytest.skip(
            "缺少低权限用户 DSN (TRANSHUB_TEST_USER_DATABASE__URL)，跳过 RLS 相关测试"
        )

    db_name = migrated_db.url.database
    low_privilege_dsn = f"{low_privilege_dsn_base.rstrip('/')}/{db_name}"

    # 在高权限连接上，为低权限用户授权并应用 RLS 策略
    async with migrated_db.begin() as conn:
        # 授权
        await conn.execute(
            text(f'GRANT CONNECT ON DATABASE "{db_name}" TO transhub_tester;')
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"
            )
        )

        # 应用 RLS 函数和策略 (测试友好版)
        await conn.execute(
            text(
                r"""
                CREATE OR REPLACE FUNCTION th.allowed_projects() RETURNS TEXT[] LANGUAGE plpgsql STABLE AS $$
                DECLARE v TEXT := current_setting('th.allowed_projects', true);
                BEGIN
                  IF v IS NULL THEN RETURN NULL; END IF;
                  IF btrim(v) = '' THEN RETURN ARRAY[]::TEXT[]; END IF;
                  RETURN string_to_array(regexp_replace(v, '\s+', '', 'g'), ',');
                END; $$;
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
                    'events','comments','locales_fallbacks','tm_units','tm_links',
                    'outbox_events'
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

    # 创建并返回低权限引擎
    engine = create_async_engine(low_privilege_dsn)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def uow_factory_rls(rls_engine: AsyncEngine) -> UowFactory:
    """提供一个使用【低权限】引擎的 UoW 工厂（专用于 RLS 集成测试）。"""
    from trans_hub.infrastructure.db import create_async_sessionmaker
    from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork

    sessionmaker = create_async_sessionmaker(rls_engine)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)
