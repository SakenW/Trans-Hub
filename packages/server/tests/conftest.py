# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v6.1 · 最终导入修复版)

核心优化:
- [最终修复] 添加了所有缺失的导入，解决了 `NameError`。
- 坚持使用 `Base.metadata.create_all` 的方案，因为它最稳定、最可靠，
  并完全避免了 sync/async 混合调用的时序问题。
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
# [修复] 导入 create_async_engine
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
# [修复] 导入 ORM Base 用于 create_all
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
    [最终方案] 提供一个引擎，它连接到一个全新的、已通过 ORM `create_all`
    初始化的临时数据库。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip("维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置")

    maint_url = make_url(raw_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        async_dsn = temp_db_url.render_as_string(hide_password=False).replace("+psycopg", "+asyncpg")
        
        # 1. 直接创建异步引擎
        eng = create_async_engine(async_dsn)

        # 2. 使用 Base.metadata.create_all 在异步连接上创建所有表
        async with eng.begin() as conn:
            # 关键步骤：先创建 schema
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
            # 然后创建所有表
            await conn.run_sync(Base.metadata.create_all)
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
    # 关键：确保 coordinator 使用与 uow_factory 相同的数据库
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
        # 授权逻辑可能需要根据 create_all 的情况调整，但基本相同
        await conn.execute(text(f"GRANT CONNECT ON DATABASE \"{db_name}\" TO transhub_tester;"))
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"))
        await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA th GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO transhub_tester;"))

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