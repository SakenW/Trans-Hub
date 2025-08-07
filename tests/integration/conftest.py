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

# --- [核心修改] 导入 Alembic ---
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
    not PG_DATABASE_URL.startswith("postgres"),
    reason="需要设置 TH_DATABASE_URL 为 PostgreSQL 连接字符串以运行此测试",
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """配置全局测试环境，对整个测试会话生效一次。"""
    TEST_DIR.mkdir(exist_ok=True)
    yield
    # 为了调试，暂时禁用测试后的自动清理
    # if os.getenv("CI") is None:
    #     shutil.rmtree(TEST_DIR)


# --- [核心修改] 新增 Alembic 迁移辅助函数 ---
def _run_migrations(db_url: str):
    """
    一个辅助函数，用于在测试环境中以编程方式运行 Alembic 迁移。
    它会动态地将测试用的数据库 URL 传递给 Alembic。
    """
    # 确定 alembic.ini 的绝对路径
    alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
    if not alembic_cfg_path.is_file():
        raise FileNotFoundError(f"Alembic config not found at {alembic_cfg_path}")

    # 创建 Alembic 配置对象
    alembic_cfg = Config(str(alembic_cfg_path))

    # [关键] 覆盖 alembic.ini 中的 sqlalchemy.url，使其指向我们的临时测试数据库
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 执行升级到最新版本 ("head")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def test_config() -> TransHubConfig:
    """为每个测试提供一个隔离的 TransHubConfig 实例（默认使用 SQLite）。"""
    db_file = f"e2e_test_{os.urandom(4).hex()}.db"
    # 使用绝对路径以避免相对路径问题
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
    
    # 确保父目录存在
    if db_url.startswith("sqlite:///"):
        db_file_path = Path(test_config.db_path)
        db_file_path.parent.mkdir(parents=True, exist_ok=True)

    # --- [核心修改] 使用 Alembic 进行数据库初始化 ---
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

    main_dsn = PG_DATABASE_URL
    parsed = urlparse(main_dsn)
    db_name = f"test_db_{os.urandom(4).hex()}"
    server_dsn = parsed._replace(path="").geturl()

    conn = await asyncpg.connect(dsn=server_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    test_db_dsn = parsed._replace(path=f"/{db_name}").geturl()

    # --- [核心修改] 使用 Alembic 进行数据库初始化 ---
    _run_migrations(test_db_dsn)

    handler = create_persistence_handler(TransHubConfig(database_url=test_db_dsn))
    await handler.connect()
    yield handler
    await handler.close()

    conn = await asyncpg.connect(dsn=server_dsn)
    try:
        await conn.execute(f'DROP DATABASE "{db_name}" WITH (FORCE)')
    finally:
        await conn.close()