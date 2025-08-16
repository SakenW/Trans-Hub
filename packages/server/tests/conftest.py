# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v3.0.0 重构版)

- 复用 tests.helpers.db_manager 中的工具函数来创建和销毁主测试数据库。
- 确保测试环境的准备逻辑与迁移测试的逻辑共享相同的底层实现。
"""
from __future__ import annotations

import pytest_asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
    dispose_engine,
)
from trans_hub.infrastructure.db._schema import Base
from tests.helpers.db_manager import create_db, drop_db, resolve_maint_dsn


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """强制 pytest-asyncio 使用 asyncio 后端。"""
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def engine() -> AsyncEngine:
    """
    会话级共享引擎, 自动在会话开始时重建主测试数据库。
    """
    # 1. 加载测试配置以获取数据库名
    cfg = create_app_config(env_mode="test")
    app_db_name = cfg.database.url.split("/")[-1]
    assert app_db_name.startswith("transhub_test"), "测试数据库名必须以 'transhub_test' 开头"

    # 2. 复用 db_manager 的工具来获取维护库 DSN
    maint_url = resolve_maint_dsn()

    # 3. 复用 db_manager 的工具来销毁和创建数据库
    drop_db(maint_url, app_db_name)
    create_db(maint_url, app_db_name)

    # 4. 异步操作：创建 schema 和所有表
    eng = create_async_db_engine(cfg)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    await dispose_engine(eng)
    # 会话结束后，可以选择保留或删除主测试库，这里选择保留以方便调试
    # drop_db(maint_url, app_db_name)


@pytest.fixture(scope="session")
def sessionmaker(engine: AsyncEngine):
    """提供一个会话级的异步 Session 工厂。"""
    return create_async_sessionmaker(engine)


@pytest_asyncio.fixture
async def coordinator(engine: AsyncEngine, sessionmaker) -> Coordinator:
    """提供一个函数级的、已初始化的 Coordinator 实例。"""
    cfg = create_app_config(env_mode="test")
    coord = Coordinator(cfg)

    coord._engine = engine
    coord._sessionmaker = sessionmaker

    await coord.initialize()
    try:
        yield coord
    finally:
        await coord.close()