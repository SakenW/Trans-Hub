# packages/server/tests/integration/infrastructure/db/migrations/test_migrations_cycle.py
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

# [最终修复] 导入 bootstrap 以获取配置
from trans_hub.bootstrap.init import create_app_config

# [最终修复] 更新导入路径
from tests.helpers.tools.db_manager import (
    _alembic_ini,
    _cfg_safe,
    managed_temp_database,
)

pytestmark = [pytest.mark.db, pytest.mark.migrations, pytest.mark.slow]


@pytest.mark.asyncio
async def test_upgrade_downgrade_cycle_on_temp_db() -> None:
    """
    在一个由上下文管理器保证生命周期的临时数据库上，
    执行升级→降级→再升级的完整闭环测试。
    """
    # 1. 获取维护 DSN
    test_config = create_app_config(env_mode="test")
    raw_maint_dsn = test_config.maintenance_database_url
    if not raw_maint_dsn:
        pytest.skip("维护库 DSN 未配置")
    maint_url = make_url(raw_maint_dsn)

    async with managed_temp_database(maint_url) as temp_db_url:
        # 2. 加载 Alembic 配置
        alembic_ini_path = _alembic_ini()
        cfg = Config(str(alembic_ini_path))

        # 3. 注入临时库 DSN
        tenant_real_dsn = temp_db_url.render_as_string(hide_password=False)
        cfg.set_main_option("sqlalchemy.url", _cfg_safe(tenant_real_dsn))

        # 4. 执行测试循环
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
