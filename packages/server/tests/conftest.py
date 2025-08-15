# packages/server/tests/conftest.py
"""
Pytest 共享夹具（全链路异步，遵守技术宪章）

- 仅使用包级公共 API：trans_hub.infrastructure.db
- 测试开始时建表并做一次连通性检查；测试结束统一 await 释放连接池。
"""

from __future__ import annotations

import pytest_asyncio
import pytest
from sqlalchemy import text
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
    """让 pytest-asyncio/anyio 使用 asyncio 事件循环。"""
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncEngine:
    """
    会话级共享引擎：
    - 基于严格模式加载的配置创建
    - 执行建表与 SELECT 1 连通性检查
    - 会话结束统一释放（await dispose）
    """
    cfg = load_config_from_env(mode="test", strict=True)
    eng = create_async_db_engine(cfg)
    async with eng.begin() as conn:
        # 在测试开始前，清理掉旧的 schema 和 public schema 中的所有内容
        await conn.execute(text("DROP SCHEMA IF EXISTS th CASCADE;"))
        await conn.execute(text("CREATE SCHEMA th;"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SELECT 1"))
    
    yield eng
    
    await dispose_engine(eng)


@pytest.fixture(scope="session")
def sessionmaker(engine: AsyncEngine):
    """提供异步 Session 工厂给各测试模块使用。"""
    return create_async_sessionmaker(engine)


@pytest_asyncio.fixture
async def coordinator(engine: AsyncEngine, sessionmaker) -> Coordinator:
    """
    提供一个已初始化的 Coordinator。
    [REFACTOR] 使用 pytest_asyncio.fixture 并确保正确的异步清理。
    """
    cfg = load_config_from_env(mode="test", strict=True)
    coord = Coordinator(cfg)
    
    # 最小侵入式依赖注入
    coord._engine = engine
    coord._sessionmaker = sessionmaker
    
    await coord.initialize()
    try:
        yield coord
    finally:
        # 确保在异步 fixture 的 finally 块中 await 关闭操作
        await coord.close()