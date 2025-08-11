# packages/server/tests/conftest.py
"""
为 `server` 包的集成测试提供共享的 Fixtures。
(v17 - 使用统一加载器 load_config_from_env；只读测试环境（严格模式）；构建/迁移临时测试库）
"""
import asyncio
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine as create_sync_engine, text
from sqlalchemy.engine.url import make_url, URL
from sqlalchemy.ext.asyncio import AsyncEngine

# --- 保证能导入 server/src 下的项目模块 ---
SRC_DIR = Path(__file__).resolve().parents[1] / "src"  # packages/server/src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.config import TransHubConfig
from trans_hub.config_loader import load_config_from_env
from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import Base


# -------------------------------
# 会话级：事件循环
# -------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """为整个测试会话创建一个事件循环，避免不同测试间的干扰。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# -------------------------------
# 会话级：加载测试配置（严格模式）
# -------------------------------
@pytest.fixture(scope="session")
def config() -> TransHubConfig:
    """
    仅读取测试环境配置：优先 packages/server/.env.test（严格模式，不回退到 .env）。
    也允许通过 CI 环境变量直接注入（如 TH_DATABASE_URL）。
    """
    try:
        cfg = load_config_from_env(mode="test", strict=True)
    except Exception as e:
        pytest.fail(f"测试启动失败：无法加载测试配置（.env.test 或环境变量）。错误：{e}")
    return cfg


# -------------------------------
# 会话级：创建并迁移“临时测试库”，结束后销毁
# -------------------------------
@pytest_asyncio.fixture(scope="session")
async def db_engine(config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    - 使用维护库（psycopg2 同步）创建/销毁测试数据库
    - 在该库上运行 Alembic 迁移（同步）
    - 应用/测试使用异步引擎（通常 asyncpg），结束后清理
    """
    app_db_url_str = config.database_url
    maint_db_url_str = config.maintenance_database_url

    if not app_db_url_str or not app_db_url_str.startswith("postgresql"):
        pytest.fail("TH_DATABASE_URL 未正确配置为 PostgreSQL 连接串。")
    if not maint_db_url_str:
        pytest.fail("TH_MAINTENANCE_DATABASE_URL 未配置，无法进行建库/删库管理。")

    app_url = make_url(app_db_url_str)
    maint_url = make_url(maint_db_url_str)

    test_db_name = f"test_db_{uuid.uuid4().hex[:8]}"

    # 同步维护库引擎（管理操作稳定）
    sync_maint_url = URL.create(
        drivername="postgresql+psycopg2",
        username=maint_url.username,
        password=maint_url.password,
        host=maint_url.host,
        port=maint_url.port,
        database=maint_url.database or "postgres",
    )
    sync_engine = create_sync_engine(sync_maint_url, isolation_level="AUTOCOMMIT")

    # 1) 创建测试数据库
    try:
        with sync_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    except Exception as e:
        pytest.fail(f"创建测试数据库失败，请确认权限（CREATEDB）与网络：{e}")

    # 2) 运行 Alembic 迁移（同步 psycopg2）
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        server_root = Path(__file__).resolve().parents[1]  # packages/server
        alembic_ini = server_root / "alembic.ini"
        if not alembic_ini.is_file():
            pytest.fail(f"未找到 Alembic 配置文件：{alembic_ini}")

        alembic_cfg = AlembicConfig(str(alembic_ini))

        sync_test_url = URL.create(
            drivername="postgresql+psycopg2",
            username=maint_url.username,
            password=maint_url.password,
            host=maint_url.host,
            port=maint_url.port,
            database=test_db_name,
        )
        alembic_cfg.set_main_option("sqlalchemy.url", str(sync_test_url))

        sl = alembic_cfg.get_main_option("script_location")
        if sl:
            sl_path = Path(sl)
            if not sl_path.is_absolute():
                sl_path = (alembic_ini.parent / sl_path).resolve()
            alembic_cfg.set_main_option("script_location", str(sl_path))

        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        with sync_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{test_db_name}" WITH (FORCE)'))
        pytest.fail(f"Alembic 迁移失败：{e}")

    # 3) 创建异步引擎供测试使用（沿用 app_url 的 driver，通常 asyncpg）
    async_test_url = str(app_url.set(database=test_db_name))
    try:
        from trans_hub.infrastructure.db._session import create_db_engine
        engine: AsyncEngine = create_db_engine(TransHubConfig(database_url=async_test_url))
    except Exception as e:
        with sync_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{test_db_name}" WITH (FORCE)'))
        pytest.fail(f"创建异步引擎失败：{e}")

    try:
        yield engine
    finally:
        await engine.dispose()
        with sync_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{test_db_name}" WITH (FORCE)'))
        sync_engine.dispose()


# -------------------------------
# 函数级：Coordinator（每个测试干净表）
# -------------------------------
@pytest_asyncio.fixture
async def coordinator(db_engine: AsyncEngine, config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    """
    每个测试前确保表结构干净，然后提供一个连接到测试库的 Coordinator。
    """
    # 1) 清表
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # 2) 基于原配置复制一份，并覆盖为当前测试库 URL
    test_config = config.copy(deep=True)
    test_config.database_url = str(db_engine.url)

    coord = Coordinator(test_config)
    await coord.initialize()
    try:
        yield coord
    finally:
        await coord.close()