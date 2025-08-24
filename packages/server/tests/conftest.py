# packages/server/tests/conftest.py
"""
Pytest 共享夹具 (v7.0 · DI Container 驱动版)

核心 Fixtures:
- migrated_db: 提供一个独立的、包含了所有 Schema 和行为（RLS, 触发器）的临时数据库引擎。
- app_container: (会话级) 提供一个完全初始化并装配好(wired)的 DI 容器实例，是所有注入依赖的来源。
- uow_factory: (函数级) 从 app_container 获取 UoW 工厂，用于在测试中与数据库交互。
- coordinator: (函数级) 从 app_container 获取 Coordinator 实例，用于测试应用服务层。
- rls_engine / uow_factory_rls: 用于 RLS 测试的低权限数据库连接和 UoW 工厂。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncGenerator, Generator

import nest_asyncio
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# --- [关键修复] 允许在测试中嵌套 asyncio.run() ---
nest_asyncio.apply()


# --- [关键修复] 导入路径修复，确保 pytest 能找到 'trans_hub' 包 ---
TESTS_DIR = Path(__file__).parent
SERVER_PACKAGE_ROOT = TESTS_DIR.parent
SRC_DIR = SERVER_PACKAGE_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 业务侧依赖 ---
from trans_hub.application.coordinator import Coordinator
from trans_hub.config import TransHubConfig
from trans_hub.di.container import AppContainer
from trans_hub.infrastructure.db import create_async_sessionmaker, dispose_engine
from trans_hub.infrastructure.db._schema import Base
from trans_hub.infrastructure.uow import SqlAlchemyUnitOfWork, UowFactory

from tests.helpers.tools.db_manager import (
    managed_temp_database,
    managed_temp_database_sync,
)
from trans_hub.management.config_utils import get_real_db_url


def run_migrations(engine: Engine, db_schema: str | None):
    """使用给定的引擎运行 alembic 迁移。"""
    from trans_hub.management.config_utils import get_real_db_url
    
    print(f"[DEBUG] 开始执行迁移，目标schema: {db_schema}")
    
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", "alembic")
    # 不设置sqlalchemy.url，让env.py使用注入的引擎
    alembic_cfg.set_main_option("db_schema", db_schema or "public")
    
    print(f"[DEBUG] Alembic配置: script_location=alembic, db_schema={db_schema}")
    print(f"[DEBUG] 引擎URL: {engine.url}")

    # [v3.3 修复] 在调用 Alembic 之前，显式创建 schema 并提交。
    # 这确保了 schema 在 Alembic 尝试访问它之前是完全持久化和可见的。
    if db_schema and db_schema != "public":
        print(f"[DEBUG] 创建schema: {db_schema}")
        with engine.connect() as connection:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {db_schema}"))
            connection.commit()  # 关键：确保 schema 创建被提交
            print(f"[DEBUG] Schema {db_schema} 创建完成")

    # 将应用的元数据注入到 Alembic 上下文中，以确保它使用与应用相同的模型定义。
    # 注意：不在这里设置 metadata.schema，让 env.py 根据配置自行处理
    metadata = Base.metadata
    alembic_cfg.attributes["target_metadata"] = metadata
    
    print("[DEBUG] 开始执行Alembic迁移...")
    try:
        # [关键修复] 在事务中执行迁移，确保正确提交
        with engine.begin() as connection:
            # 直接传递连接给 Alembic，确保在同一事务中执行
            alembic_cfg.attributes["connection"] = connection
            
            # 将迁移升级到最新版本
            command.upgrade(alembic_cfg, "head")
            print("[DEBUG] 迁移执行完成，事务将自动提交")
        
        print("[DEBUG] 迁移事务已提交")
        
    except Exception as e:
        print(f"[DEBUG] 迁移执行失败: {e}")
        raise


# =========================
# 核心夹具
# =========================


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """强制 pytest-asyncio 使用 asyncio 后端。"""
    return "asyncio"


@pytest.fixture(scope="session")
def test_config() -> TransHubConfig:
    """提供一个会话级配置对象，加载 .env 并设置测试环境。"""
    # 使用统一的配置加载入口，包含数据库连接验证
    from trans_hub.bootstrap.init import load_config_with_validation

    return load_config_with_validation(env_mode="test")


@pytest_asyncio.fixture(scope="session")
async def migrated_db(test_config: TransHubConfig) -> AsyncGenerator[AsyncEngine, None]:
    """
    (会话级) 提供一个通过 Alembic 完全迁移到最新版本的临时数据库引擎。
    为整个测试会话创建一个单一的数据库，以提高性能。
    警告：测试之间不是隔离的，需要额外的清理机制。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip(
            "维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置，跳过数据库相关测试"
        )

    # 获取真实的维护库 URL（包含真实密码）
    real_maint_dsn = get_real_db_url(raw_maint_dsn)
    maint_url = make_url(real_maint_dsn)
    async with managed_temp_database(maint_url) as temp_db_url:
        # 1. 创建同步引擎，用于执行 Alembic 迁移
        sync_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+asyncpg", "+psycopg"
        )
        sync_engine = create_engine(sync_dsn)

        # 2. 执行迁移（使用事务确保正确提交）
        alembic_ini_path = SERVER_PACKAGE_ROOT / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))
        db_schema = alembic_cfg.get_main_option("db_schema", "public")
        
        # 使用连接注入的方式在事务中执行迁移
        with sync_engine.begin() as connection:
            alembic_cfg.attributes["connection"] = connection
            command.upgrade(alembic_cfg, "head")

        # 3. 在同一个事务中执行其他数据库设置
        with sync_engine.begin() as connection:
            # 为测试主用户授予 BYPASSRLS 权限
            current_user = connection.scalar(text("SELECT current_user"))
            connection.execute(text(f'ALTER USER "{current_user}" BYPASSRLS'))

            # 创建低权限测试角色
            connection.execute(
                text(r"""
                DO $$
                BEGIN
                   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'transhub_tester') THEN
                      CREATE ROLE transhub_tester WITH LOGIN PASSWORD 'password';
                   END IF;
                END $$;
            """)
            )

        # 4. 确保同步引擎正确关闭
        sync_engine.dispose()

        # 4. 为测试创建并提供异步引擎
        # 获取真实的临时数据库 URL（包含真实密码）
        real_temp_dsn = get_real_db_url(temp_db_url.render_as_string(hide_password=False))
        async_dsn = real_temp_dsn
        # 对于asyncpg，使用URL参数设置schema
        if db_schema and db_schema != "public":
            # 使用URL参数设置search_path
            separator = "&" if "?" in async_dsn else "?"
            async_dsn += f"{separator}options=-csearch_path%3D{db_schema}%2Cpublic"
        async_engine = create_async_engine(async_dsn)

        try:
            yield async_engine
        finally:
            await dispose_engine(async_engine)


@pytest.fixture(scope="session")
def sync_migrated_db(test_config: TransHubConfig) -> Generator[Engine, None, None]:
    """
    (会话级) 提供一个同步的、通过 Alembic 完全迁移的临时数据库引擎。
    """
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip(
            "维护库 DSN (TRANSHUB_MAINTENANCE_DATABASE_URL) 未配置，跳过数据库相关测试"
        )

    maint_url = make_url(raw_maint_dsn)
    with managed_temp_database_sync(maint_url) as temp_db_url:
        sync_dsn = temp_db_url.render_as_string(hide_password=False)
        sync_engine = create_engine(sync_dsn)

        # 直接在引擎上执行迁移
        alembic_ini_path = SERVER_PACKAGE_ROOT / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))
        db_schema = alembic_cfg.get_main_option("db_schema", "public")
        run_migrations(sync_engine, db_schema)

        try:
            yield sync_engine
        finally:
            sync_engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def app_container(
    migrated_db: AsyncEngine, test_config: TransHubConfig
) -> AsyncGenerator[AppContainer, None]:
    """
    (会话级) 提供一个完全初始化并装配好(wired)的 DI 容器实例。

    [v3.0 修复] 此版本绕过了 `bootstrap_app`，手动构建和配置容器，
    以确保在容器初始化之前，`db_schema` 就从 `alembic.ini` 加载并设置完毕。
    这解决了因配置加载时机不当而导致的 `schema "th" does not exist` 和
    `AttributeError`。
    """
    # 1. 从 alembic.ini 加载权威的 schema 名称
    alembic_ini_path = SERVER_PACKAGE_ROOT / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    db_schema = alembic_cfg.get_main_option("db_schema", "public")

    # 2. 基于会话配置，创建最终的函数级配置对象
    # 保留原有数据库配置，只更新schema
    updated_database = test_config.database.model_copy(
        update={"default_schema": db_schema}
    )
    final_config = test_config.model_copy(
        update={"database": updated_database}
    )

    # 3. 手动实例化和配置容器
    container = AppContainer()
    container.config.override(final_config)
    container.db_engine.override(migrated_db)  # 使用已迁移的数据库
    
    # 重新创建 sessionmaker 以使用新的 engine
    sessionmaker = create_async_sessionmaker(migrated_db)
    container.db_sessionmaker.override(sessionmaker)

    # 4. 装配需要注入依赖的模块
    container.wire(
        modules=[
            "trans_hub.adapters.cli.main",
            "trans_hub.adapters.cli.commands.db",
            "trans_hub.adapters.cli.commands.request",
            "trans_hub.adapters.cli.commands.status",
            "trans_hub.adapters.cli.commands.worker",
            "tests.e2e.cli.test_cli_smoke_flow",
        ]
    )

    yield container

    # 5. 清理异步资源
    # 检查 redis_client 资源是否需要清理
    if hasattr(container, 'redis_client') and container.redis_client.initialized:
        await container.shutdown_resources()


@pytest.fixture
def uow_factory(app_container: AppContainer) -> UowFactory:
    """(函数级) 从 DI 容器获取 UoW 工厂。"""
    return app_container.uow_factory


@pytest.fixture
def coordinator(app_container: AppContainer) -> Coordinator:
    """(函数级) 从 DI 容器获取 Coordinator 实例。"""
    return app_container.coordinator()


@pytest_asyncio.fixture(scope="function")
async def rls_engine(
    migrated_db: AsyncEngine,
    test_config: TransHubConfig,
) -> AsyncGenerator[AsyncEngine, None]:
    """
    (会话级) 提供一个使用【低权限】测试用户连接的引擎，用于 RLS 测试。
    """
    low_privilege_dsn_base = test_config.test_user_database_url
    if not low_privilege_dsn_base:
        pytest.skip(
            "缺少低权限用户 DSN (TRANSHUB_TEST_USER_DATABASE_URL)，跳过 RLS 相关测试"
        )

    db_name = migrated_db.url.database
    low_privilege_dsn = f"{low_privilege_dsn_base}{db_name}"

    async with migrated_db.begin() as conn:
        await conn.execute(
            text(f'GRANT CONNECT ON DATABASE "{db_name}" TO transhub_tester;')
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA th TO transhub_tester;"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA th TO transhub_tester;"
            )
        )
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA th GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO transhub_tester;"
            )
        )
        await conn.execute(
            text("GRANT EXECUTE ON FUNCTION th.allowed_projects() TO transhub_tester;")
        )
        await conn.execute(
            text(
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA th TO transhub_tester;"
            )
        )

    eng = create_async_engine(low_privilege_dsn)
    try:
        yield eng
    finally:
        await dispose_engine(eng)


@pytest.fixture
def uow_factory_rls(rls_engine: AsyncEngine) -> UowFactory:
    """(函数级) 提供一个使用【低权限】引擎的 UoW 工厂。"""
    sessionmaker = create_async_sessionmaker(rls_engine)
    return lambda: SqlAlchemyUnitOfWork(sessionmaker)
