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

from alembic import command
from alembic.config import Config

from trans_hub import Coordinator, EngineName, TransHubConfig
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.engine_registry import discover_engines
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler

if TYPE_CHECKING:
    pass

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


def _run_migrations(db_url: str):
    """
    一个同步的辅助函数，用于在测试环境中以编程方式运行 Alembic 迁移。
    """
    alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    if not alembic_cfg_path.is_file():
        raise FileNotFoundError(f"Alembic config not found at {alembic_cfg_path}")

    alembic_cfg = Config(str(alembic_cfg_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def test_config() -> TransHubConfig:
    """为每个测试提供一个隔离的 TransHubConfig 实例（默认使用 SQLite）。"""
    db_file = f"e2e_test_{os.urandom(4).hex()}.db"
    db_path = (TEST_DIR / db_file).resolve()
    return TransHubConfig(
        database_url=f"sqlite:///{db_path}",
        active_engine=EngineName.DEBUG,
        source_lang="en",
    )


@pytest_asyncio.fixture
async def coordinator(
    test_config: TransHubConfig,
) -> AsyncGenerator[Coordinator, None]:
    """提供一个完全初始化、可用于端到端测试的真实 Coordinator 实例 (SQLite)。"""
    db_url = test_config.database_url
    if db_url.startswith("sqlite:///"):
        db_file_path = Path(test_config.db_path)
        db_file_path.parent.mkdir(parents=True, exist_ok=True)

    _run_migrations(db_url)

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

    main_dsn_sqlalchemy = PG_DATABASE_URL
    parsed = urlparse(main_dsn_sqlalchemy)
    db_name = f"test_db_{os.urandom(4).hex()}"
    
    # --- [核心修复] 创建一个 asyncpg 能理解的 DSN 用于管理操作 ---
    main_dsn_asyncpg = main_dsn_sqlalchemy.replace("postgresql+asyncpg", "postgresql", 1)
    parsed_asyncpg = urlparse(main_dsn_asyncpg)
    server_dsn_asyncpg = parsed_asyncpg._replace(path="").geturl()

    conn = None
    try:
        conn = await asyncpg.connect(dsn=server_dsn_asyncpg)
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        if conn:
            await conn.close()
    
    # 用于 Alembic 和 TransHubConfig 的 DSN (SQLAlchemy 格式)
    test_db_dsn_sqlalchemy = parsed._replace(path=f"/{db_name}").geturl()

    _run_migrations(test_db_dsn_sqlalchemy)

    handler_config = TransHubConfig(database_url=test_db_dsn_sqlalchemy)
    handler = create_persistence_handler(handler_config)
    await handler.connect()
    
    yield handler
    
    await handler.close()

    try:
        conn = await asyncpg.connect(dsn=server_dsn_asyncpg)
        await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    finally:
        if conn:
            await conn.close()