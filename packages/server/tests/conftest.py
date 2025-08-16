# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v3.0.3 · 绝对正确版)

核心修复：
- 修正了 v3.0.2 版本中因 `PostgresPersistenceHandler` 构造函数缺少 `dsn` 参数
  而导致的 `TypeError`。
- 使用 `create_persistence_handler` 工厂函数来重新构建 `coordinator.handler`，
  而不是手动实例化。这确保了所有依赖项都按预期正确传递，代码也更健壮。
- 保持了 v3.0.2 的核心思想：每个测试函数使用一个完全独立的数据库和 Coordinator
  实例，以实现最高的测试隔离性。
"""

from __future__ import annotations
from typing import AsyncGenerator

import pytest_asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_app_config
from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db import (
    create_async_db_engine,
    create_async_sessionmaker,
    dispose_engine,
)
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.persistence import create_persistence_handler
from tests.helpers.db_manager import managed_temp_database


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
    函数作用域引擎，为每个测试创建一个全新的临时数据库。
    """
    async with managed_temp_database() as temp_db_url:
        # 动态修改配置以指向临时数据库
        original_db_url = test_config.database.url
        test_config.database.url = temp_db_url.render_as_string(hide_password=False).replace(
            "+psycopg", "+asyncpg"
        )
        
        eng = create_async_db_engine(test_config)
        async with eng.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
            await conn.run_sync(Base.metadata.create_all)

        yield eng

        await dispose_engine(eng)
        # 恢复原始配置，以防其他 session-scoped fixtures 需要它
        test_config.database.url = original_db_url


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """提供一个绑定到函数级引擎的 Session 工厂。"""
    return create_async_sessionmaker(engine)


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[Coordinator, None]:
    """
    提供一个完全隔离的、与函数级引擎绑定的 Coordinator 实例。
    """
    # 1. 创建 Coordinator，它会基于 test_config 初始化自己的（临时的）引擎和 handler
    coord = Coordinator(config=test_config)
    
    # 2. 销毁 Coordinator 自己创建的那个临时引擎
    await dispose_engine(coord._engine)

    # 3. 注入由 fixture 管理的、生命周期正确的引擎和 sessionmaker
    coord._engine = engine
    coord._sessionmaker = sessionmaker
    
    # 4. [最终修复] 使用工厂函数重新创建 handler，确保所有依赖都正确传入
    coord.handler = create_persistence_handler(test_config, sessionmaker)

    # 5. 现在可以安全地初始化了
    await coord.initialize()

    yield coord
    
    await coord.close()