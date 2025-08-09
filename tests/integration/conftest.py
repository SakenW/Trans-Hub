# tests/integration/conftest.py
# [v2.4 Refactor] 集成测试核心 Fixture 配置
import asyncio
import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config as AlembicConfig
from trans_hub.config import EngineName, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.db.schema import Base
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# ---- 全局初始化 ----
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "WARNING"), log_format="console")

TEST_DIR = Path(__file__).parent.parent / "test_output"
# 从环境变量获取数据库 URL，这是 CI 的标准做法
PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")
if not PG_DATABASE_URL or not PG_DATABASE_URL.startswith("postgresql"):
    pytest.fail(
        "PostgreSQL 集成测试需要设置 TH_DATABASE_URL 环境变量，并以 'postgresql://' 或 'postgresql+asyncpg://' 开头。"
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境，对整个测试会话生效一次。"""
    TEST_DIR.mkdir(exist_ok=True, parents=True)
    yield
    # 在非 CI 环境下，测试结束后清理输出目录
    if os.getenv("CI") is None and TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)


def run_migrations(connection_url: str):
    """一个同步的辅助函数，用于运行 Alembic 迁移。"""
    alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    alembic_cfg = AlembicConfig(str(alembic_cfg_path))
    # Alembic 需要一个同步的数据库 URL
    sync_db_url = connection_url.replace("+asyncpg", "")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    """[Session Scoped] 确保数据库存在并已应用所有迁移，返回其 URL。"""
    # 确保 URL 包含 asyncpg 驱动
    db_url = PG_DATABASE_URL
    if "postgresql://" in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    run_migrations(db_url)
    return db_url


@pytest_asyncio.fixture
async def db_engine(migrated_db_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """[Function Scoped] 为每个测试创建一个独立的、全新的 Engine。"""
    engine = create_async_engine(migrated_db_url)
    # 在测试开始前，清空所有表的数据，确保隔离性
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield engine
    # 测试结束后，安全关闭并销毁引擎
    await engine.dispose()


@pytest_asyncio.fixture
async def handler(db_engine: AsyncEngine) -> AsyncGenerator[PersistenceHandler, None]:
    """[Function Scoped] 提供一个已连接的、使用独立引擎的持久化处理器。"""
    # 使用与引擎相同的 URL 来构造配置
    config = TransHubConfig(database_url=str(db_engine.url))
    
    # 覆盖 sessionmaker 的绑定，确保它使用我们为本测试创建的独立引擎
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    
    # 因为 create_persistence_handler 内部会创建自己的引擎，我们在此处手动构造
    from trans_hub.persistence.postgres import PostgresPersistenceHandler
    handler_instance = PostgresPersistenceHandler(session_factory, dsn=str(db_engine.url))
    
    await handler_instance.connect()
    yield handler_instance
    await handler_instance.close()


@pytest_asyncio.fixture
async def coordinator(handler: PersistenceHandler) -> AsyncGenerator[Coordinator, None]:
    """[Function Scoped] 提供一个已初始化的、连接到真实DB的 Coordinator。"""
    # 确保 Coordinator 使用与 handler 相同的配置
    config = TransHubConfig(
        database_url=str(handler._sessionmaker.kw["bind"].url),
        active_engine=EngineName.DEBUG, # 默认使用 Debug 引擎以提高测试速度和确定性
        source_lang="en",
    )
    coord = Coordinator(config, handler)
    await coord.initialize()
    yield coord
    await coord.close()