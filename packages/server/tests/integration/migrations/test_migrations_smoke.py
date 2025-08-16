# packages/server/tests/integration/migrations/test_migrations_smoke.py
"""
迁移冒烟测试 (v3.0.0 重构版)

本测试利用 `managed_temp_database` 上下文管理器来确保测试环境的
绝对纯净和零残留。核心逻辑只关注 Alembic 命令本身的正确性。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from tests.helpers.db_manager import managed_temp_database

pytestmark = pytest.mark.asyncio


def _alembic_ini() -> Path:
    """定位 alembic.ini 文件。"""
    # ... (此函数保持不变) ...
    # 本文件: packages/server/tests/integration/migrations/test_migrations_smoke.py
    # .parents[3] 导航到 packages/server
    server_root = Path(__file__).resolve().parents[3]
    ini = server_root / "alembic.ini"
    if not ini.exists():
        pytest.fail(f"未找到 alembic.ini 在预期的位置: {ini}")
    return ini


def _cfg_safe(value: str) -> str:
    """为 configparser 安全地转义 '%' 符号。"""
    return value.replace("%", "%%")


async def test_upgrade_downgrade_cycle_on_temp_db() -> None:
    """
    在一个由上下文管理器保证生命周期的临时数据库上，
    执行升级→降级→再升级的完整闭环测试。
    """
    async with managed_temp_database(prefix="th_migrate_") as temp_db_url:
        # 1. 加载 Alembic 配置
        alembic_ini_path = _alembic_ini()
        cfg = Config(str(alembic_ini_path))

        # 2. 将临时数据库的 DSN 注入 Alembic 配置
        # DSN 必须是同步的，由 db_manager 提供
        tenant_real_dsn = temp_db_url.render_as_string(hide_password=False)
        cfg.set_main_option("sqlalchemy.url", _cfg_safe(tenant_real_dsn))

        print(
            f"Running migration cycle on: {temp_db_url.render_as_string(hide_password=True)}"
        )

        # 3. 执行升级 -> 降级 -> 升级的完整循环
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

        # 上下文管理器退出时，将自动、可靠地删除临时数据库
