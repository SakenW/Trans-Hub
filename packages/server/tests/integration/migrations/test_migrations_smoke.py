# packages/server/tests/integration/migrations/test_migrations_smoke.py
# -*- coding: utf-8 -*-
"""
迁移冒烟测试（最终优化版）
目标：
1) 使用“维护库 DSN”动态创建临时库；
2) 读取 alembic.ini，仅覆盖 sqlalchemy.url，完全信任 ini 文件中的 script_location；
3) 在临时库上执行 upgrade('head') → downgrade('base') → upgrade('head')；
4) 强制回收连接并 DROP 临时库，环境不留痕。

关键点：
- 完全依赖 alembic.ini 的 script_location 配置，不再手动覆盖。
- 若检出 URL 密码为 '***' 或为空，则从环境变量注入真实密码。
- CREATE/DROP DATABASE 必须在 AUTOCOMMIT 会话中执行。
- 所有日志仅打印“脱敏 URL”。
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Final

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError

try:
    from psycopg.errors import InsufficientPrivilege
except ImportError:
    # 如果 psycopg 未安装，创建一个占位符异常类
    InsufficientPrivilege = type("InsufficientPrivilege", (Exception,), {})


SAFE_DBNAME_RE: Final = re.compile(r"^[a-z0-9_]+$")
ENV_KEY_MAINT_DSN: Final = "TRANSHUB_MAINTENANCE_DATABASE_URL"
ENV_KEY_MAINT_PWD: Final = "TRANSHUB_MAINTENANCE_DATABASE_PASSWORD"


# ----------------------------- 工具函数 ----------------------------- #
def _server_root() -> Path:
    """获取 packages/server 目录的路径。"""
    # 本文件: packages/server/tests/integration/migrations/test_migrations_smoke.py
    # .parents[3] 导航到 packages/server
    return Path(__file__).resolve().parents[3]


def _alembic_ini() -> Path:
    """定位 alembic.ini 文件。"""
    ini = _server_root() / "alembic.ini"
    if not ini.exists():
        # 回退检查项目根目录，增加灵活性
        ini_root = _server_root().parent.parent / "alembic.ini"
        if ini_root.exists():
            return ini_root
        raise AssertionError(f"未找到 alembic.ini：{ini}")
    return ini


def _print_masked(label: str, raw_dsn: str) -> None:
    """安全地打印脱敏后的 DSN。"""
    try:
        url = make_url(raw_dsn)
        print(f"[{label}] sqlalchemy.url =", url.render_as_string(hide_password=True))
    except Exception:
        print(f"[{label}] sqlalchemy.url = (unparsed, hidden)")


def _resolve_maint_dsn() -> str:
    """解析维护库 DSN，并处理密码占位符。"""
    raw = os.getenv(ENV_KEY_MAINT_DSN, "").strip()
    if not raw:
        pytest.skip(f"缺少 {ENV_KEY_MAINT_DSN}，跳过迁移冒烟测试")
    
    # [v3.0.0 宪章对齐] 严格要求 psycopg 驱动
    if not raw.startswith("postgresql+psycopg"):
        pytest.skip(f"{ENV_KEY_MAINT_DSN} 必须为 psycopg 驱动，当前为: {raw!r}")

    url = make_url(raw)
    pwd = (url.password or "").strip()

    if pwd in ("", "***"):
        inject = os.getenv(ENV_KEY_MAINT_PWD) or os.getenv("PGPASSWORD")
        if not inject:
            pytest.fail(
                "检测到维护库 URL 的密码为空或为 '***'（脱敏占位）。\n"
                f"请设置 {ENV_KEY_MAINT_PWD} 或 PGPASSWORD 为真实口令；"
                f"或把 {ENV_KEY_MAINT_DSN} 直接写入真实口令。"
            )
        url = url._replace(password=inject)

    _print_masked("maint_dsn.effective", url.render_as_string(hide_password=True))
    return url.render_as_string(hide_password=False)


def _gen_temp_dbname() -> str:
    """生成一个安全的临时数据库名称。"""
    name = f"th_migrate_test_{uuid.uuid4().hex[:8]}"
    assert SAFE_DBNAME_RE.match(name), f"临时库名不合法：{name}"
    return name


def _make_db_dsn(base_real_dsn: str, dbname: str) -> str:
    """根据基础 DSN 和新库名构建一个完整的 DSN。"""
    url = make_url(base_real_dsn)._replace(database=dbname)
    return url.render_as_string(hide_password=False)


def _terminate_connections(maint_real_dsn: str, dbname: str) -> None:
    """强制终止到指定数据库的所有连接。"""
    eng = create_engine(maint_real_dsn)
    try:
        with eng.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": dbname},
            )
    finally:
        eng.dispose()


def _ddl_autocommit(maint_real_dsn: str, sql: str) -> None:
    """在 AUTOCOMMIT 模式下执行一条 DDL 语句。"""
    eng = create_engine(maint_real_dsn, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(text(sql))
    finally:
        eng.dispose()


def _drop_db_if_exists(maint_real_dsn: str, dbname: str) -> None:
    """如果存在，则安全地删除数据库。"""
    _terminate_connections(maint_real_dsn, dbname)
    _ddl_autocommit(maint_real_dsn, f'DROP DATABASE IF EXISTS "{dbname}"')


def _create_db(maint_real_dsn: str, dbname: str) -> None:
    """创建数据库，并处理权限不足的情况。"""
    try:
        _ddl_autocommit(maint_real_dsn, f'CREATE DATABASE "{dbname}" ENCODING \'UTF8\'')
    except OperationalError as e:
        if InsufficientPrivilege and isinstance(e.orig, InsufficientPrivilege):
            pytest.skip("维护账号缺少 CREATEDB 权限，跳过迁移冒烟测试（请为该角色授予 CREATEDB）")
        raise


def _cfg_safe(value: str) -> str:
    """为 configparser 安全地转义 '%' 符号。"""
    return value.replace("%", "%%")


# ----------------------------- 主测试 ----------------------------- #
def test_upgrade_downgrade_cycle_on_temp_db() -> None:
    """
    执行升级→降级→再升级的完整闭环测试。
    """
    maint_real_dsn = _resolve_maint_dsn()
    temp_db = _gen_temp_dbname()
    tenant_real_dsn = _make_db_dsn(maint_real_dsn, temp_db)

    _drop_db_if_exists(maint_real_dsn, temp_db)
    _create_db(maint_real_dsn, temp_db)

    try:
        # 1. 加载 Alembic 配置，完全信任 alembic.ini 的设置
        alembic_ini_path = _alembic_ini()
        cfg = Config(str(alembic_ini_path))

        # 2. 仅覆盖数据库 URL
        _print_masked("tenant_dsn.effective", tenant_real_dsn)
        cfg.set_main_option("sqlalchemy.url", _cfg_safe(tenant_real_dsn))

        # 3. 执行升级 -> 降级 -> 升级的完整循环
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

    finally:
        # 4. 无论成功与否，都确保清理临时数据库
        _drop_db_if_exists(maint_real_dsn, temp_db)