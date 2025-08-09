# tests/integration/conftest.py
"""为所有集成测试提供共享的、真实的 Fixtures (UIDA 架构版)。"""
import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from alembic.config import Config
from trans_hub.config import EngineName, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# ---- 全局初始化 ----
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "INFO"), log_format="console")
discover_engines()

TEST_DIR = Path(__file__).parent.parent / "test_output"

PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    not PG_DATABASE_URL.startswith("postgresql+asyncpg"),
    reason="需要设置 TH_DATABASE_URL 为 postgresql+asyncpg://... 格式来运行此测试",
)


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
    # [核心修复] Alembic 需要同步驱动
    sync_db_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def test_sqlite_db_url() -> str:
    """为每个测试提供一个隔离的、基于文件的 SQLite 数据库 URL。"""
    db_file = f"integration_test_{os.urandom(4).hex()}.db"
    db_path = (TEST_DIR / db_file).resolve()
    return f"sqlite+aiosqlite:///{db_path}"


@pytest_asyncio.fixture
async def sqlite_handler(test_sqlite_db_url: str) -> AsyncGenerator[PersistenceHandler, None]:
    """提供一个连接到临时 SQLite 数据库并应用了 Schema 的 PersistenceHandler。"""
    _run_migrations(test_sqlite_db_url)
    config = TransHubConfig(database_url=test_sqlite_db_url)
    handler = create_persistence_handler(config)
    await handler.connect()
    yield handler
    await handler.close()


@pytest_asyncio.fixture
async def postgres_handler() -> AsyncGenerator[PersistenceHandler, None]:
    """提供一个连接到临时 PostgreSQL 测试数据库并应用了 Schema 的 PersistenceHandler。"""
    import asyncpg
    from urllib.parse import urlparse

    main_dsn = PG_DATABASE_URL
    parsed_main = urlparse(main_dsn)
    db_name = f"test_db_{os.urandom(4).hex()}"
    server_dsn = main_dsn.replace(parsed_main.path, "/postgres")

    conn = await asyncpg.connect(server_dsn.replace("+asyncpg", ""))
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    await conn.close()

    test_db_dsn = main_dsn.replace(parsed_main.path, f"/{db_name}")
    _run_migrations(test_db_dsn)

    config = TransHubConfig(database_url=test_db_dsn)
    handler = create_persistence_handler(config)
    await handler.connect()
    yield handler
    await handler.close()

    conn = await asyncpg.connect(server_dsn.replace("+asyncpg", ""))
    await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    await conn.close()


# [核心修复] 新增共享的、参数化的 handler fixture
@pytest.fixture(
    params=[
        pytest.param("sqlite_handler", id="sqlite"),
        pytest.param("postgres_handler", id="postgres", marks=requires_postgres),
    ]
)
def handler(request: pytest.FixtureRequest) -> PersistenceHandler:
    """为测试提供参数化的、不同数据库后端的 PersistenceHandler。"""
    return request.getfixturevalue(request.param)


# [核心修复] 新增 coordinator fixture，解决 E2E 测试的根本问题
@pytest_asyncio.fixture
async def coordinator(handler: PersistenceHandler) -> AsyncGenerator[Coordinator, None]:
    """提供一个已初始化的、连接到真实测试数据库的 Coordinator 实例。"""
    # Coordinator 的配置应与 handler 的数据库保持一致
    if hasattr(handler, "dsn"):  # Postgres handler
        db_url = handler.dsn
    else:  # SQLite handler
        db_url = f"sqlite+aiosqlite:///{handler.db_path}"

    config = TransHubConfig(
        database_url=db_url,
        active_engine=EngineName.DEBUG,  # 使用 Debug 引擎进行可预测的测试
        source_lang="en",  # 为测试设置默认源语言
    )
    coord = Coordinator(config, handler)
    await coord.initialize()
    yield coord
    await coord.close()