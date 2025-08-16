# packages/server/tests/integration/migrations/test_migrations_smoke.py
# -*- coding: utf-8 -*-
"""
迁移冒烟测试（文件优先 · psycopg3 · 自建/删临时库 · AUTOCOMMIT · 支持脱敏占位兜底）
目标：
1) 使用“维护库 DSN”（系统库，如 postgres）动态创建临时库；
2) 读取仓库内 alembic.ini（单一事实来源），仅覆盖 sqlalchemy.url；
3) 在临时库上执行 upgrade('head') → downgrade('base') → upgrade('head')；
4) 强制回收连接并 DROP 临时库，环境不留痕。

关键点：
- 若检出 URL 密码为 '***' 或为空，则从 TRANSHUB_MAINTENANCE_DATABASE_PASSWORD（或 PGPASSWORD）注入真实密码；
- CREATE/DROP DATABASE 必须在 AUTOCOMMIT 会话中执行；
- 所有日志仅打印“脱敏 URL”，绝不打印明文密码。

需要的环境变量：
- TRANSHUB_MAINTENANCE_DATABASE_URL="postgresql+psycopg://user:***@host:5432/postgres"  # 允许用 *** 做占位
- 可选：TRANSHUB_MAINTENANCE_DATABASE_PASSWORD="真实口令"  # 当 URL 中是 *** 或空密码时使用
- 可选：PGPASSWORD="真实口令"  # 作为兜底回退（若上者未设置）
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
    from psycopg.errors import InsufficientPrivilege  # 更友好提示
except Exception:  # pragma: no cover
    InsufficientPrivilege = None  # type: ignore

SAFE_DBNAME_RE: Final = re.compile(r"^[a-z0-9_]+$")
ENV_KEY_MAINT_DSN: Final = "TRANSHUB_MAINTENANCE_DATABASE_URL"
ENV_KEY_MAINT_PWD: Final = "TRANSHUB_MAINTENANCE_DATABASE_PASSWORD"


# ----------------------------- 工具函数 ----------------------------- #
def _server_root() -> Path:
    # 本文件：packages/server/tests/integration/migrations/test_migrations_smoke.py
    # parents[3] == packages/server
    return Path(__file__).resolve().parents[3]


def _alembic_ini() -> Path:
    ini = _server_root() / "alembic.ini"
    if not ini.exists():
        raise AssertionError(f"未找到 alembic.ini：{ini}")
    return ini


def _print_masked(label: str, raw_dsn: str) -> None:
    """打印脱敏 DSN（仅用于排障），绝不打印明文。"""
    try:
        url = make_url(raw_dsn)
        print(f"[{label}] sqlalchemy.url =", url.render_as_string(hide_password=True))
    except Exception:
        print(f"[{label}] sqlalchemy.url = (unparsed, hidden)")


def _resolve_maint_dsn() -> str:
    """
    解析维护库 DSN：
    - 只接受 psycopg3 同步驱动；
    - 如发现密码为 '***' 或为空：尝试用 ENV_KEY_MAINT_PWD，若无则回退 PGPASSWORD；
    - 返回“未脱敏”的真实连接串（用于连接），打印时一律脱敏。
    """
    raw = os.getenv(ENV_KEY_MAINT_DSN, "").strip()
    if not raw:
        pytest.skip(f"缺少 {ENV_KEY_MAINT_DSN}，跳过迁移冒烟测试")
    if not (raw.startswith("postgresql+psycopg://") or raw.startswith("postgresql+psycopg:")):
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
        # 用真实口令重建 URL
        url = URL.create(
            drivername=url.drivername,
            username=url.username,
            password=inject,
            host=url.host,
            port=url.port,
            database=url.database,
            query=url.query,
        )

    # 打印脱敏串便于排障
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
        password=url.password,  # 保留真实口令
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
        _ddl_autocommit(maint_real_dsn, f'CREATE DATABASE "{dbname}" ENCODING \'UTF8\'')
    except Exception as e:
        if InsufficientPrivilege and isinstance(e, InsufficientPrivilege):
            pytest.skip("维护账号缺少 CREATEDB 权限，跳过迁移冒烟测试（请为该角色授予 CREATEDB）")
        raise


def _cfg_safe(value: str) -> str:
    """写入 Config 时对 '%' 做转义，避免 configparser 插值报错。"""
    return value.replace("%", "%%")


# ----------------------------- 主测试 ----------------------------- #
def test_upgrade_downgrade_cycle_on_temp_db() -> None:
    """
    升级→降级→再升级闭环：
    1) 解析维护库 DSN（必要时用专用密码变量兜底），在系统库中创建临时库；
    2) 读取 alembic.ini，仅覆盖 sqlalchemy.url（未脱敏）；
    3) 升级 → 降级 → 再升级；
    4) 回收连接并删除临时库。
    """
    maint_real_dsn = _resolve_maint_dsn()
    temp_db = _gen_temp_dbname()
    tenant_real_dsn = _make_db_dsn(maint_real_dsn, temp_db)

    # 1) 防御式清理 → 创建临时库
    _drop_db_if_exists(maint_real_dsn, temp_db)
    _create_db(maint_real_dsn, temp_db)

    try:
        # 2) 文件优先：读取 alembic.ini，仅覆盖 sqlalchemy.url
        cfg = Config(str(_alembic_ini()))
        _print_masked("tenant_dsn.effective", tenant_real_dsn)  # 脱敏打印
        cfg.set_main_option("sqlalchemy.url", _cfg_safe(tenant_real_dsn))

        # 3) 升级 → 降级 → 再升级
        try:
            command.upgrade(cfg, "head")
            command.downgrade(cfg, "base")
            command.upgrade(cfg, "head")
        except OperationalError as oe:
            _print_masked("OperationalError DSN", tenant_real_dsn)
            raise oe
    finally:
        # 4) 强制回收连接 → DROP 临时库
        _drop_db_if_exists(maint_real_dsn, temp_db)
