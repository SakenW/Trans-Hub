# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v4.3 · ORM 交互最终版)

核心优化:
- 将 `sessionmaker` 夹具重命名为 `db_sessionmaker`，使其职责更清晰：
  提供一个绑定到已迁移数据库的 `async_sessionmaker` 实例。
- 强调所有需要与 ORM 对象交互的测试，都应该依赖此夹具来获取 `AsyncSession`。
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
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker

# 导入路径修复
TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR.parent))

from tests.helpers.tools.db_manager import _alembic_ini, _cfg_safe, managed_temp_database
from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import dispose_engine, create_async_sessionmaker
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.persistence import create_persistence_handler

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
async def engine(test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    提供一个连接到全新的、完全空的临时数据库的【高权限】引擎。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip("维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未在 .env.test 中配置")
    maint_url = make_url(raw_maint_dsn)
    
    async with managed_temp_database(maint_url) as temp_db_url:
        original_db_url = test_config.database.url
        temp_db_dsn_str = temp_db_url.render_as_string(hide_password=False)
        test_config.database.url = temp_db_dsn_str.replace("+psycopg", "+asyncpg")
        
        eng = create_async_engine(test_config.database.url)
        yield eng
        await dispose_engine(eng)
        
        test_config.database.url = original_db_url

# --- 数据库状态准备夹具 ---

@pytest_asyncio.fixture
async def migrated_db(engine: AsyncEngine) -> AsyncGenerator[AsyncEngine, None]:
    """
    依赖 `engine` (高权限)，并在其上运行 Alembic 迁移到 head。
    """
    sync_dsn = engine.url.render_as_string(hide_password=False).replace("+asyncpg", "+psycopg")
    
    alembic_cfg = Config(str(_alembic_ini()))
    alembic_cfg.set_main_option("sqlalchemy.url", _cfg_safe(sync_dsn))
    
    command.upgrade(alembic_cfg, "head")
    yield engine

@pytest_asyncio.fixture
async def created_all_db(engine: AsyncEngine) -> AsyncGenerator[AsyncEngine, None]:
    """
    依赖 `engine` (高权限)，并在其上运行 `Base.metadata.create_all()`。
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    
# [关键优化] 将 sessionmaker 夹具重命名并明确其职责
@pytest.fixture
def db_sessionmaker(migrated_db: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    提供一个绑定到【已迁移数据库】的 Session 工厂。
    这是所有需要进行 ORM 操作的测试都应该使用的核心夹具。
    """
    return create_async_sessionmaker(migrated_db)

# --- RLS 测试专用夹具 (保持不变) ---
@pytest_asyncio.fixture
async def rls_engine(migrated_db: AsyncEngine, test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    # ... (此夹具保持不变)
    pass

# --- 应用层夹具 ---

@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
    migrated_db: AsyncEngine,
    db_sessionmaker: async_sessionmaker[AsyncSession], # 依赖新的夹具
) -> AsyncGenerator[Coordinator, None]:
    """
    提供一个连接到由 Alembic 完全准备好的【高权限】数据库的 Coordinator 实例。
    """
    coord = Coordinator(config=test_config)
    await dispose_engine(coord._engine)
    
    coord._engine = migrated_db
    coord._sessionmaker = db_sessionmaker # 使用夹具提供的 sessionmaker
    coord.handler = create_persistence_handler(test_config, db_sessionmaker)
    
    await coord.initialize()
    yield coord
    await coord.close()
