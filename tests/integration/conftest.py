# tests/integration/conftest.py
"""为所有集成测试提供共享的、真实的 Fixtures。"""

import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from trans_hub import Coordinator, EngineName, TransHubConfig
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

if TYPE_CHECKING:
    pass

load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "INFO"), log_format="console")
discover_engines()

TEST_DIR = Path(__file__).parent.parent / "test_output"

# v3.25 修复：从主环境变量决定是否跳过 PG 测试
PG_DATABASE_URL = os.getenv("TH_DATABASE_URL", "")
requires_postgres = pytest.mark.skipif(
    not PG_DATABASE_URL.startswith("postgres"),
    reason="需要设置 TH_DATABASE_URL 为 PostgreSQL 连接字符串以运行此测试",
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境，对整个测试会话生效一次。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    if os.getenv("CI") is None:
        shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    """为每个测试提供一个隔离的 TransHubConfig 实例（默认使用 SQLite）。"""
    db_file = f"e2e_test_{os.urandom(4).hex()}.db"
    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
) -> AsyncGenerator[Coordinator, None]:
    """提供一个完全初始化、可用于端到端测试的真实 Coordinator 实例 (SQLite)。"""
    db_path = test_config.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    apply_migrations(db_path)

    handler: PersistenceHandler = create_persistence_handler(test_config)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()

    yield coord

    await coord.close()


@pytest_asyncio.fixture
@requires_postgres
async def postgres_handler() -> AsyncGenerator[PersistenceHandler, None]:
    """提供一个连接到临时测试数据库并应用了 Schema 的 PostgresPersistenceHandler。"""
    import asyncpg  # 延迟导入

    # 从主 DSN 解析出用于连接主服务器的 DSN
    main_dsn = PG_DATABASE_URL
    parsed = urlparse(main_dsn)
    db_name = f"test_db_{os.urandom(4).hex()}"
    # DSN to connect to the server, but not a specific database
    server_dsn = parsed._replace(path="").geturl()

    conn = await asyncpg.connect(dsn=server_dsn)
    # 使用 force 选项来处理 CI 环境中可能存在的连接残留
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    await conn.close()

    test_db_dsn = parsed._replace(path=f"/{db_name}").geturl()

    schema_path = (
        Path(__file__).parent.parent.parent
        / "trans_hub/db/migrations_postgres/001_initial.sql"
    )
    sql_script = schema_path.read_text("utf-8")
    conn = await asyncpg.connect(dsn=test_db_dsn)
    await conn.execute(sql_script)
    await conn.close()

    handler = create_persistence_handler(TransHubConfig(database_url=test_db_dsn))
    await handler.connect()
    yield handler
    await handler.close()

    conn = await asyncpg.connect(dsn=server_dsn)
    await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    await conn.close()
