# packages/server/tests/conftest.py
"""
为 `server` 包的集成测试提供共享的 Fixtures。
统一使用 config_loader.load_config_from_env(mode="test") 加载配置。
"""

import asyncio
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine as create_sync_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

# --- 路径设置 ---
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from trans_hub.config import TransHubConfig
from trans_hub.config_loader import load_config_from_env
from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import Base


@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建一个事件循环，避免不同测试间的干扰。"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config() -> TransHubConfig:
    """
    [会话级 Fixture] 加载一次测试环境配置。
    只认 `.env.test`，不回退到正式环境。
    """
    return load_config_from_env(mode="test", strict=True)


@pytest_asyncio.fixture(scope="session")
async def db_engine(config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """[会话级 Fixture] 创建一个独立的测试数据库"""
    app_db_url_str = config.database_url
    maintenance_db_url_str = config.maintenance_database_url

    if not app_db_url_str or not app_db_url_str.startswith("postgresql"):
        pytest.skip("集成测试需要 PostgreSQL。")
    if not maintenance_db_url_str:
        pytest.skip("缺少 TH_MAINTENANCE_DATABASE_URL。")

    app_url = make_url(app_db_url_str)
    maintenance_url = make_url(maintenance_db_url_str)
    test_db_name = f"test_db_{uuid.uuid4().hex[:8]}"

    # 创建数据库
    sync_engine = create_sync_engine(
        str(maintenance_url.set(drivername="postgresql+psycopg2")),
        isolation_level="AUTOCOMMIT"
    )
    with sync_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {test_db_name}"))

    # Alembic 迁移
    from alembic import command
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        str(app_url.set(drivername="postgresql+psycopg2", database=test_db_name))
    )
    command.upgrade(alembic_cfg, "head")

    # 异步引擎
    from trans_hub.infrastructure.db._session import create_db_engine
    engine = create_db_engine(
        TransHubConfig(database_url=str(app_url.set(database=test_db_name)))
    )

    yield engine

    # 清理
    await engine.dispose()
    with sync_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE {test_db_name} WITH (FORCE)"))
    sync_engine.dispose()


@pytest_asyncio.fixture
async def coordinator(db_engine: AsyncEngine, config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """为每个测试函数提供一个干净数据库的 Coordinator 实例"""
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    test_config = config.copy(deep=True)
    test_config.database_url = str(db_engine.url)

    coord = Coordinator(test_config)
    await coord.initialize()
    yield coord
    await coord.close()
