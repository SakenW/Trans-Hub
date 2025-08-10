# tests/integration/conftest.py
# [v2.4.12 Final Architecture] 根除所有死锁和连接问题。
# 采用最稳健的模式：每个测试函数都创建、迁移并销毁一个完全独立的数据库。
import asyncio
import os
import shutil
import uuid
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command
from alembic.config import Config as AlembicConfig
from trans_hub.config import EngineName, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.logging_config import setup_logging

# ---- 全局初始化 ----
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "WARNING"), log_format="console")

TEST_DIR = Path(__file__).parent.parent / "test_output"
PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")


@pytest.fixture(scope="session", autouse=True)
def check_db_url_is_set():
    if not PG_DATABASE_URL or not PG_DATABASE_URL.startswith("postgresql"):
        pytest.fail(
            "PostgreSQL 集成测试需要 TH_DATABASE_URL 环境变量，指向维护库（如 '.../postgres'）。"
        )


# --- URL 配置 ---
parsed_main_url = urlparse(PG_DATABASE_URL)
MAINTENANCE_DB_URL_SYNC = parsed_main_url._replace(
    path="/postgres", scheme="postgresql"
).geturl()
ASYNC_URL_TEMPLATE = parsed_main_url._replace(
    path="/{db_name}", scheme="postgresql+asyncpg"
).geturl()
SYNC_URL_TEMPLATE = parsed_main_url._replace(
    path="/{db_name}", scheme="postgresql"
).geturl()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境。"""
    TEST_DIR.mkdir(exist_ok=True, parents=True)
    yield
    if os.getenv("CI") is None and TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)


def _manage_database_sync(db_name: str, action: str):
    """纯同步地创建或删除数据库。这是一个阻塞函数。"""
    engine = create_sync_engine(MAINTENANCE_DB_URL_SYNC, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        if action == "create":
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        elif action == "drop":
            conn.execute(text(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity WHERE pg_stat_activity.datname = '{db_name}';
            """))
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    engine.dispose()


def _run_migrations_sync(db_url: str):
    """纯同步地运行 Alembic 迁移。这是一个阻塞函数。"""
    alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    alembic_cfg = AlembicConfig(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    [Function Scoped, Async] 为每个测试创建一个独立的、全新的、已迁移的数据库和引擎。
    """
    test_db_name = f"test_db_{uuid.uuid4().hex}"
    
    # [核心修正] 将所有阻塞的同步操作委托给独立的线程
    await asyncio.to_thread(_manage_database_sync, test_db_name, "create")
    
    test_db_url_sync = SYNC_URL_TEMPLATE.format(db_name=test_db_name)
    await asyncio.to_thread(_run_migrations_sync, test_db_url_sync)
    
    test_db_url_async = ASYNC_URL_TEMPLATE.format(db_name=test_db_name)
    engine = create_async_engine(test_db_url_async)
    try:
        yield engine
    finally:
        await engine.dispose()
        await asyncio.to_thread(_manage_database_sync, test_db_name, "drop")


@pytest_asyncio.fixture
async def handler(db_engine: AsyncEngine) -> AsyncGenerator[PersistenceHandler, None]:
    """提供一个已连接的、使用独立数据库引擎的持久化处理器。"""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    from trans_hub.persistence.postgres import PostgresPersistenceHandler
    handler_instance = PostgresPersistenceHandler(session_factory, dsn=str(db_engine.url))
    await handler_instance.connect()
    yield handler_instance
    await handler_instance.close()


@pytest_asyncio.fixture
async def coordinator(handler: PersistenceHandler) -> AsyncGenerator[Coordinator, None]:
    """提供一个已初始化的、连接到独立测试数据库的 Coordinator。"""
    config = TransHubConfig(
        database_url=str(handler._sessionmaker.kw["bind"].url),
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )
    coord = Coordinator(config, handler)
    await coord.initialize()
    yield coord
    await coord.close()