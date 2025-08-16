# packages/server/tests/integration/migrations/test_migrations_smoke.py
# -*- coding: utf-8 -*-
"""
迁移冒烟测试（最终简化版）
目标：
1) 使用“维护库 DSN”动态创建临时库；
2) 读取 alembic.ini，仅覆盖 sqlalchemy.url，完全信任 ini 文件中的 script_location；
3) 在临时库上执行 upgrade('head') → downgrade('base') → upgrade('head')；
4) 强制回收连接并 DROP 临时库，环境不留痕。
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
except Exception:
    InsufficientPrivilege = None

SAFE_DBNAME_RE: Final = re.compile(r"^[a-z0-9_]+$")
ENV_KEY_MAINT_DSN: Final = "TRANSHUB_MAINTENANCE_DATABASE_URL"
ENV_KEY_MAINT_PWD: Final = "TRANSHUB_MAINTENANCE_DATABASE_PASSWORD"


# ----------------------------- 工具函数 ----------------------------- #
def _server_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _alembic_ini() -> Path:
    ini = _server_root() / "alembic.ini"
    if not ini.exists():
        raise AssertionError(f"未找到 alembic.ini：{ini}")
    return ini


def _print_masked(label: str, raw_dsn: str) -> None:
    try:
        url = make_url(raw_dsn)
        print(f"[{label}] sqlalchemy.url =", url.render_as_string(hide_password=True))
    except Exception:
        print(f"[{label}] sqlalchemy.url = (unparsed, hidden)")


def _resolve_maint_dsn() -> str:
    raw = os.getenv(ENV_KEY_MAINT_DSN, "").strip()
    if not raw:
        pytest.skip(f"缺少 {ENV_KEY_MAINT_DSN}，跳过迁移冒烟测试")
    if not (
        raw.startswith("postgresql+psycopg://") or raw.startswith("postgresql+psycopg:")
    ):
        pytest.skip(f"{ENV_KEY_MAINT_DSN} 必须为 psycopg3 驱动：{raw!r}")

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
        url = URL.create(
            drivername=url.drivername,
            username=url.username,
            password=inject,
            host=url.host,
            port=url.port,
            database=url.database,
            query=url.query,
        )

    _print_masked("maint_dsn.effective", url.render_as_string(hide_password=True))
    return url.render_as_string(hide_password=False)


def _gen_temp_dbname() -> str:
    name = f"th_migrate_test_{uuid.uuid4().hex[:8]}"
    assert SAFE_DBNAME_RE.match(name), f"临时库名不合法：{name}"
    return name


def _make_db_dsn(base_real_dsn: str, dbname: str) -> str:
    url = make_url(base_real_dsn)
    new_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=dbname,
        query=url.query,
    )
    return new_url.render_as_string(hide_password=False)


def _terminate_connections(maint_real_dsn: str, dbname: str) -> None:
    eng = create_engine(maint_real_dsn, future=True)
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
    eng = create_engine(maint_real_dsn, future=True)
    try:
        with eng.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(sql)
    finally:
        eng.dispose()


def _drop_db_if_exists(maint_real_dsn: str, dbname: str) -> None:
    _terminate_connections(maint_real_dsn, dbname)
    _ddl_autocommit(maint_real_dsn, f'DROP DATABASE IF EXISTS "{dbname}"')


def _create_db(maint_real_dsn: str, dbname: str) -> None:
    try:
        _ddl_autocommit(maint_real_dsn, f"CREATE DATABASE \"{dbname}\" ENCODING 'UTF8'")
    except Exception as e:
        if InsufficientPrivilege and isinstance(e, InsufficientPrivilege):
            pytest.skip(
                "维护账号缺少 CREATEDB 权限，跳过迁移冒烟测试（请为该角色授予 CREATEDB）"
            )
        raise


def _cfg_safe(value: str) -> str:
    return value.replace("%", "%%")


# ----------------------------- 主测试 ----------------------------- #
def test_upgrade_downgrade_cycle_on_temp_db() -> None:
    """
    升级→降级→再升级闭环。
    """
    maint_real_dsn = _resolve_maint_dsn()
    temp_db = _gen_temp_dbname()
    tenant_real_dsn = _make_db_dsn(maint_real_dsn, temp_db)

    _drop_db_if_exists(maint_real_dsn, temp_db)
    _create_db(maint_real_dsn, temp_db)

    try:
        alembic_ini_path = _alembic_ini()
        cfg = Config(str(alembic_ini_path))

        _print_masked("tenant_dsn.effective", tenant_real_dsn)
        cfg.set_main_option("sqlalchemy.url", _cfg_safe(tenant_real_dsn))

        # [关键修复] 删除显式的 script_location 设置，完全信任 alembic.ini
        # script_location = alembic_ini_path.parent / "alembic"
        # cfg.set_main_option("script_location", str(script_location))

        try:
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "base")
            command.upgrade(cfg, "head")
        except OperationalError as oe:
            _print_masked("OperationalError DSN", tenant_real_dsn)
            raise oe
    finally:
        _drop_db_if_exists(maint_real_dsn, temp_db)
