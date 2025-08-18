# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v5.0 · UoW 架构重构版)

核心优化:
- `coordinator` 夹具成为所有应用层集成测试的唯一入口点。它通过 bootstrap
  创建一个完整的、连接到隔离临时数据库的应用实例。
- 新增 `uow_factory` 夹具，专用于持久化层（仓库）的集成测试，提供对
  UoW 的直接访问。
- 废弃旧的 `db_sessionmaker`，其职责已被 UoW 吸收。
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# 导入路径修复
TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR.parent))

from tests.helpers.tools.db_manager import (
    _alembic_ini,
    _cfg_safe,
    managed_temp_database,
)
from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import (
    create_app_config,
    create_coordinator,
    create_uow_factory,
)
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import dispose_engine
from trans_hub.infrastructure.uow import UowFactory


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
    提供一个引擎，它连接到一个全新的、已通过 Alembic 迁移到 'head' 的临时数据库。
    这是所有需要数据库的测试的基础。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip(
            "维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未在 .env.test 中配置"
        )

    maint_url = make_url(raw_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        # 1. 更新配置以指向临时数据库
        original_db_url = test_config.database.url
        temp_db_dsn_str = temp_db_url.render_as_string(hide_password=False)
        test_config.database.url = temp_db_dsn_str.replace("+psycopg", "+asyncpg")

        # 2. 运行 Alembic 迁移
        sync_dsn_for_alembic = test_config.database.url.replace("+asyncpg", "+psycopg")
        alembic_cfg = Config(str(_alembic_ini()))
        alembic_cfg.set_main_option("sqlalchemy.url", _cfg_safe(sync_dsn_for_alembic))
        command.upgrade(alembic_cfg, "head")

        # 3. 创建并移交引擎
        eng = create_async_engine(test_config.database.url)
        yield eng

        # 4. 清理
        await dispose_engine(eng)
        test_config.database.url = original_db_url


# --- 应用层与持久化层夹具 ---


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,  # 依赖于已迁移的数据库
) -> AsyncGenerator[Coordinator, None]:
    """
    [推荐] 提供一个连接到隔离临时数据库的、完全初始化的 Coordinator 实例。
    这是应用层集成测试的首选夹具。
    """
    # bootstrap.create_coordinator 会创建自己的引擎，我们需要替换它
    coord, eng = await create_coordinator(test_config)
    await dispose_engine(eng)  # 关闭并丢弃 bootstrap 创建的默认引擎

    # 创建一个连接到 `migrated_db` 的新 UoW 工厂并注入
    uow_factory, _ = create_uow_factory(test_config)
    coord._uow_factory = uow_factory

    yield coord
    # 清理 coordinator 内部可能持有的资源 (如果 close 方法有实现)
    await coord.close()


@pytest.fixture
def uow_factory(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,  # 同样依赖于已迁移的数据库
) -> UowFactory:
    """
    [底层] 提供一个直接连接到隔离临时数据库的 UoW 工厂。
    这主要用于持久化层（仓库）的集成测试。
    """
    factory, _ = create_uow_factory(test_config)
    return factory


@pytest_asyncio.fixture
async def rls_engine(
    migrated_db: AsyncEngine,
    test_config: TransHubConfig,
) -> AsyncGenerator[AsyncEngine, None]:
    """
    提供一个使用【低权限】测试用户连接到已迁移数据库的引擎。
    """
    low_privilege_dsn_base = os.getenv("TRANSHUB_TEST_USER_DATABASE__URL")
    if not low_privilege_dsn_base:
        pytest.skip(
            "缺少低权限用户 DSN (TRANSHUB_TEST_USER_DATABASE__URL)，跳过 RLS 测试"
        )

    db_name = migrated_db.url.database
    low_privilege_dsn = f"{low_privilege_dsn_base}{db_name}"

    # 在高权限引擎上为低权限用户授权
    async with migrated_db.begin() as conn:
        await conn.execute(
            text(f"GRANT CONNECT ON DATABASE {db_name} TO transhub_tester;")
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"
            )
        )
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA th GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO transhub_tester;"
            )
        )

    eng = create_async_engine(low_privilege_dsn)
    yield eng
    await dispose_engine(eng)


@pytest.fixture
def uow_factory_rls(
    rls_engine: AsyncEngine,
) -> UowFactory:
    """
    [新增] 提供一个使用【低权限】引擎的 UoW 工厂，专用于 RLS 测试。
    """
    from trans_hub.infrastructure.db import create_async_sessionmaker
    from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork

    sessionmaker = create_async_sessionmaker(rls_engine)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)
