# packages/server/tests/helpers/db_manager.py
"""
测试数据库生命周期管理工具

本模块提供了管理临时测试数据库的单一事实来源 (SSOT)。
核心功能:
- `managed_temp_database`: 一个异步上下文管理器，保证临时数据库的
  创建、提供 DSN、并在结束后被彻底清理。
- 底层工具函数: 用于解析 DSN、创建/删除数据库，可被其他测试夹具复用。
"""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Final

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

try:
    from psycopg.errors import InsufficientPrivilege
except ImportError:
    InsufficientPrivilege = type("InsufficientPrivilege", (Exception,), {})

SAFE_DBNAME_RE: Final = re.compile(r"^[a-z0-9_]+$")
ENV_KEY_MAINT_DSN: Final = "TRANSHUB_MAINTENANCE_DATABASE_URL"


def resolve_maint_dsn() -> URL:
    """
    从环境变量安全地解析维护库 DSN，并返回 SQLAlchemy URL 对象。
    如果 DSN 不存在或驱动不正确，则跳过测试。
    """
    raw = os.getenv(ENV_KEY_MAINT_DSN, "").strip()
    if not raw:
        pytest.skip(f"缺少 {ENV_KEY_MAINT_DSN}，跳过数据库依赖测试")

    if not raw.startswith(("postgresql+psycopg", "postgresql+psycopg2")):
        pytest.skip(f"{ENV_KEY_MAINT_DSN} 必须为 psycopg 驱动，当前为: {raw!r}")

    url = make_url(raw)
    
    # Pydantic Settings v2 可能会自动从 .env 文件中加载，所以密码通常是真实的
    # 但我们保留此逻辑以应对手动设置或 CI 环境中的脱敏占位符
    if (url.password or "").strip() in ("", "***"):
        pytest.fail(
            f"维护库 URL 的密码为空或为脱敏占位符 '***'。\n"
            f"请在 .env.test 文件中为 {ENV_KEY_MAINT_DSN} 提供完整、真实的 DSN。"
        )

    return url


def create_db(maint_engine_url: URL, db_name: str) -> None:
    """在 AUTOCOMMIT 模式下创建数据库。"""
    engine = create_engine(maint_engine_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}" ENCODING \'UTF8\''))
    except Exception as e:
        if isinstance(getattr(e, "orig", None), InsufficientPrivilege):
            pytest.skip("维护账号缺少 CREATEDB 权限，跳过测试")
        raise
    finally:
        engine.dispose()


def drop_db(maint_engine_url: URL, db_name: str) -> None:
    """在 AUTOCOMMIT 模式下安全地删除数据库，并强制终止连接。"""
    engine = create_engine(maint_engine_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            # 强制终止所有到该数据库的连接
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        engine.dispose()


@asynccontextmanager
async def managed_temp_database(prefix: str = "th_test_") -> AsyncGenerator[URL, None]:
    """
    一个异步上下文管理器，用于创建、提供并保证清理一个临时数据库。

    Args:
        prefix: 临时数据库名称的前缀。

    Yields:
        一个指向新创建的临时数据库的 SQLAlchemy URL 对象。
    """
    maint_url = resolve_maint_dsn()
    temp_db_name = f"{prefix}{uuid.uuid4().hex[:8]}"
    assert SAFE_DBNAME_RE.match(temp_db_name), f"临时库名不合法：{temp_db_name}"

    temp_db_url = maint_url.set(database=temp_db_name)

    # 先清理可能存在的残留
    drop_db(maint_url, temp_db_name)
    create_db(maint_url, temp_db_name)

    try:
        yield temp_db_url
    finally:
        drop_db(maint_url, temp_db_name)