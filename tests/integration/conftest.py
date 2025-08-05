# tests/integration/conftest.py
"""为所有集成测试提供共享的、真实的 Fixtures。"""

import asyncio
import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from trans_hub import Coordinator, EngineName, TransHubConfig
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

# v3.15 修复：使用延迟导入和 TYPE_CHECKING 来处理可选依赖
if TYPE_CHECKING:
    import asyncpg

# 在测试收集阶段初始化日志和引擎发现
load_dotenv()
setup_logging(log_level=os.getenv("TEST_LOG_LEVEL", "INFO"), log_format="console")
discover_engines()

TEST_DIR = Path(__file__).parent.parent / "test_output"


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


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """从环境变量获取 PostgreSQL DSN，如果不存在则跳过测试。"""
    dsn = os.getenv("TH_TEST_POSTGRESS_DSN")
    if not dsn:
        pytest.skip("需要设置 TH_TEST_POSTGRES_DSN 环境变量以运行 PostgreSQL 测试")
    return dsn


@pytest_asyncio.fixture
async def postgres_handler(
    postgres_dsn: str,
) -> AsyncGenerator[PersistenceHandler, None]:
    """提供一个连接到测试数据库并应用了 Schema 的 PostgresPersistenceHandler。"""
    import asyncpg  # 延迟导入

    db_name = f"test_db_{os.urandom(4).hex()}"
    conn = await asyncpg.connect(postgres_dsn)
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    await conn.close()

    test_db_dsn = f"{postgres_dsn.rsplit('/', 1)[0]}/{db_name}"

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

    conn = await asyncpg.connect(postgres_dsn)
    await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    await conn.close()