# packages/server/tests/conftest.py
"""
集成测试共享 Fixtures (v34 - 终极正确版)
- 依赖升级后的 Alembic 和 python-dotenv，恢复到最理想的动态数据库创建逻辑。
- 移除了所有调试代码和 workarounds。
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

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.config import TransHubConfig
from trans_hub.config_loader import load_config_from_env
from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import Base

@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建一个事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def config() -> TransHubConfig:
    """从 .env.test 加载配置，仅执行一次。"""
    try:
        server_root = Path(__file__).parent.parent
        dotenv_file_path = server_root / ".env.test"
        return load_config_from_env(
            mode="test",
            strict=True,
            dotenv_path=dotenv_file_path
        )
    except Exception as e:
        pytest.fail(f"测试启动失败：无法加载 .env.test 配置。错误：{e}")

@pytest_asyncio.fixture(scope="session")
async def db_engine(config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """[核心 Fixture] 动态创建、迁移并销毁一个用于整个测试会话的临时数据库。"""
    maint_url = make_url(config.maintenance_database_url)
    app_url = make_url(config.database_url)
    test_db_name = f"test_db_{uuid.uuid4().hex[:8]}"

    sync_maint_engine = create_sync_engine(
        maint_url.set(drivername="postgresql+psycopg"), isolation_level="AUTOCOMMIT"
    )
    try:
        with sync_maint_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    except Exception as e:
        pytest.fail(f"创建测试数据库失败: {e}")
    
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        server_root = Path(__file__).parent.parent
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", str(server_root / "alembic"))
        
        sync_test_url = str(app_url.set(database=test_db_name, drivername="postgresql+psycopg"))
        alembic_cfg.set_main_option("sqlalchemy.url", sync_test_url)
        
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        with sync_maint_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
        pytest.fail(f"Alembic 迁移到临时数据库失败: {e}")
    
    from trans_hub.infrastructure.db._session import create_db_engine
    async_test_url = app_url.set(database=test_db_name) 
    # 创建一个临时的 config 对象，仅用于创建指向正确测试库的 engine
    engine_config = TransHubConfig(database_url=str(async_test_url), maintenance_database_url=config.maintenance_database_url)
    engine = create_db_engine(engine_config)

    try:
        yield engine
    finally:
        await engine.dispose()
        with sync_maint_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
        sync_maint_engine.dispose()

@pytest_asyncio.fixture
async def coordinator(db_engine: AsyncEngine, config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """为每个测试函数提供一个干净的、初始化完成的 Coordinator 实例。"""
    # 在每次测试前清空所有表，确保测试隔离性
    async with db_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "th"."{table.name}" RESTART IDENTITY CASCADE;'))

    # 使用指向临时数据库的 URL 来初始化 Coordinator
    temp_config = config.copy(update={"database_url": str(db_engine.url)}, deep=True)
    coord = Coordinator(temp_config)
    # 强制 Coordinator 使用由 fixture 管理的共享引擎，确保连接池一致
    coord._engine = db_engine
    
    await coord.initialize()
    try:
        yield coord
    finally:
        await coord.close()