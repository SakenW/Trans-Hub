# tests/integration/conftest.py
# [v2.3 - 修正事件循环冲突]
import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command
from alembic.config import Config
from trans_hub.config import EngineName, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.db.schema import Base
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# ---- 全局初始化 ----
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "DEBUG"), log_format="console")
discover_engines()

TEST_DIR = Path(__file__).parent.parent / "test_output"

PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")
if not PG_DATABASE_URL or not PG_DATABASE_URL.startswith("postgresql"):
    pytest.fail("PostgreSQL 测试需要设置 TH_DATABASE_URL 环境变量，并以 postgresql:// 开头。")


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境，对整个测试会话生效一次。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    if os.getenv("CI") is None and os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)


def _run_migrations(db_url: str) -> None:
    """一个同步的辅助函数，用于运行 Alembic 迁移。"""
    alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    if not alembic_cfg_path.is_file():
        raise FileNotFoundError(f"Alembic config not found at {alembic_cfg_path}")

    alembic_cfg = Config(str(alembic_cfg_path))
    sync_db_url = db_url.replace("+asyncpg", "")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    """
    [Session Scoped] 确保数据库存在并已应用迁移，然后返回其 URL。
    """
    db_url = PG_DATABASE_URL
    if not db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    _run_migrations(db_url)
    return db_url


@pytest_asyncio.fixture
async def handler(migrated_db_url: str) -> AsyncGenerator[PersistenceHandler, None]:
    """
    [Function Scoped] 为每个测试创建一个隔离的、全新的 Handler 和 Engine。
    """
    config = TransHubConfig(database_url=migrated_db_url)
    
    # 为此测试函数创建一个全新的引擎，确保它在正确的事件循环中。
    engine = create_async_engine(migrated_db_url)

    # 在测试开始前，清空所有表的数据。
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    # 使用这个专用的引擎创建 Handler
    handler = create_persistence_handler(config)
    handler._sessionmaker.kw["bind"] = engine
    await handler.connect()

    yield handler

    # 测试结束后，安全关闭并销毁引擎。
    await handler.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def coordinator(handler: PersistenceHandler) -> AsyncGenerator[Coordinator, None]:
    """提供一个已初始化的、连接到真实 PostgreSQL 测试数据库的 Coordinator 实例。"""
    config = TransHubConfig(
        database_url=PG_DATABASE_URL,
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )
    coord = Coordinator(config, handler)
    # Handler 已经连接，但 Coordinator 的 initialize 仍然需要调用
    await coord.initialize()
    yield coord
    await coord.close()