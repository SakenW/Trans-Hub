# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (最终权威版)

- engine fixture:
  - 自动在会话开始时重建测试数据库。
  - 使用 `Base.metadata.create_all` 创建与 ORM 模型完全一致的 Schema。
  - 通过在独立的事务中创建 schema，解决了 `UndefinedTableError`。
- 确保测试环境的数据库准备是简单、快速且可靠的。
"""

from __future__ import annotations
import os
from pathlib import Path

import pytest_asyncio
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from trans_hub.config_loader import load_config_from_env
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
    dispose_engine,
)
from trans_hub.infrastructure.db._schema import Base
from trans_hub.application.coordinator import Coordinator


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """强制 pytest-asyncio 使用 asyncio 后端。"""
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def engine() -> AsyncEngine:
    """
    会话级共享引擎, 自动在会话开始时重建测试数据库。
    """
    cfg = load_config_from_env(mode="test", strict=True)
    
    # --- 1. 同步操作：重建数据库 ---
    maint_url_str = cfg.maintenance_database_url
    assert maint_url_str, "TRANSHUB_MAINTENANCE_DATABASE_URL is required for tests"
    
    app_url = make_url(cfg.database.url)
    app_db_name = app_url.database
    app_db_user = app_url.username

    maint_url = make_url(maint_url_str).set(drivername="postgresql+psycopg")
    sync_maint_engine = create_engine(maint_url, isolation_level="AUTOCOMMIT")
    try:
        with sync_maint_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{app_db_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{app_db_name}" OWNER {app_db_user}'))
    finally:
        sync_maint_engine.dispose()

    # --- 2. 异步操作：创建 schema 和所有表 ---
    eng = create_async_db_engine(cfg)
    async with eng.begin() as conn:
        # [CRITICAL FIX] 先创建 schema 并提交，再创建表
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
    
    async with eng.begin() as conn:
        # 现在 schema 肯定存在，可以安全地创建所有表
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SELECT 1"))

    yield eng
    
    await dispose_engine(eng)


@pytest.fixture(scope="session")
def sessionmaker(engine: AsyncEngine):
    """提供一个会话级的异步 Session 工厂。"""
    return create_async_sessionmaker(engine)


@pytest_asyncio.fixture
async def coordinator(engine: AsyncEngine, sessionmaker) -> Coordinator:
    """提供一个函数级的、已初始化的 Coordinator 实例。"""
    cfg = load_config_from_env(mode="test", strict=True)
    coord = Coordinator(cfg)
    
    coord._engine = engine
    coord._sessionmaker = sessionmaker
    
    await coord.initialize()
    try:
        yield coord
    finally:
        await coord.close()