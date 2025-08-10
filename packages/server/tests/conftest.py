# packages/server/tests/conftest.py
"""
为 `server` 包的集成测试提供共享的 Fixtures。
(最终防御性编程版 - 强制加载 .env 文件)
"""
import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

# [核心修复] 在所有其他导入之前，首先加载 .env 文件
from dotenv import load_dotenv

# 明确指定 .env 文件的路径，以确保在任何情况下都能找到它
# pytest 从 `packages/server` 目录启动，所以 .env 就在当前目录
dotenv_path = Path.cwd() / ".env"
if dotenv_path.is_file():
    load_dotenv(dotenv_path=dotenv_path, override=True)
    print(f"\n--- [conftest.py] 成功加载 .env 文件: {dotenv_path} ---")
else:
    print(f"\n--- [conftest.py] 警告: 未找到 .env 文件: {dotenv_path} ---")


import pytest
import pytest_asyncio
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from trans_hub.application.coordinator import Coordinator
from trans_hub.config import TransHubConfig

# --- 数据库管理 ---

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """
    [会话级 Fixture] 创建一个独立的、临时的数据库用于整个测试会话。
    """
    main_db_url = os.getenv("TH_DATABASE_URL")
    print(f"--- [db_engine fixture] 读取到的 TH_DATABASE_URL: {main_db_url} ---")
    
    if not main_db_url or not main_db_url.startswith("postgresql"):
        pytest.skip("集成测试需要配置 TH_DATABASE_URL 指向 PostgreSQL。")

    from sqlalchemy.engine.url import make_url
    
    url = make_url(main_db_url)
    test_db_name = f"test_db_{uuid.uuid4().hex[:8]}"
    
    maintenance_url = url._replace(database="postgres", drivername="postgresql")
    sync_engine = create_sync_engine(maintenance_url, isolation_level="AUTOCOMMIT")

    try:
        with sync_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {test_db_name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {test_db_name}"))
    except Exception as e:
        pytest.fail(f"创建测试数据库失败，请检查用户权限（需要 CREATEDB）和连接: {e}")
    
    try:
        from alembic import command
        from alembic.config import Config
        
        alembic_cfg = Config("alembic.ini")
        sync_test_url = url._replace(database=test_db_name, drivername="postgresql").render_as_string(hide_password=False)
        alembic_cfg.set_main_option("sqlalchemy.url", sync_test_url)
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Alembic 迁移到测试数据库失败: {e}")

    async_test_url = url._replace(database=test_db_name).render_as_string(hide_password=False)
    from trans_hub.infrastructure.db._session import create_db_engine
    engine = create_db_engine(TransHubConfig(database_url=async_test_url))

    yield engine

    await engine.dispose()
    with sync_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE {test_db_name} WITH (FORCE)"))
    sync_engine.dispose()


@pytest_asyncio.fixture
async def coordinator(db_engine: AsyncEngine) -> AsyncGenerator[Coordinator, None]:
    """
    [函数级 Fixture] 为每个测试函数提供一个全新的 Coordinator 实例。
    """
    from trans_hub.infrastructure.db._schema import Base
    
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    config = TransHubConfig(database_url=str(db_engine.url))
    coord = Coordinator(config)
    await coord.initialize()
    yield coord
    await coord.close()