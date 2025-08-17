# packages/server/tests/helpers/tools/db_manager.py
"""
测试数据库生命周期管理工具 (最终纯粹版)

核心职责:
- 提供 `managed_temp_database` 上下文管理器，接收维护库 DSN 来创建/销毁临时数据库。
- 提供 Alembic 相关的辅助函数。
- 本模块不包含任何配置加载逻辑，保持职责单一。
"""
from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Final

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

try:
    from psycopg.errors import InsufficientPrivilege
except ImportError:
    InsufficientPrivilege = type("InsufficientPrivilege", (Exception,), {})

SAFE_DBNAME_RE: Final = re.compile(r"^[a-z0-9_]+$")

def create_db(maint_engine_url: URL, db_name: str) -> None:
    """在 AUTOCOMMIT 模式下创建数据库。"""
    engine = create_engine(maint_engine_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}" ENCODING \'UTF8\''))
    except Exception as e:
        # 捕获原始异常以进行更精确的检查
        orig_exc = getattr(e, "orig", None)
        if isinstance(orig_exc, InsufficientPrivilege):
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
async def managed_temp_database(maint_url: URL, prefix: str = "th_test_") -> AsyncGenerator[URL, None]:
    """
    一个纯粹的异步上下文管理器，接收一个维护库 URL 来创建和销毁临时数据库。
    """
    temp_db_name = f"{prefix}{uuid.uuid4().hex[:8]}"
    if not SAFE_DBNAME_RE.match(temp_db_name):
         raise ValueError(f"生成的临时库名不合法：{temp_db_name}")

    temp_db_url = maint_url.set(database=temp_db_name)
    
    # 先清理可能存在的残留
    drop_db(maint_url, temp_db_name)
    create_db(maint_url, temp_db_name)
    
    try:
        yield temp_db_url
    finally:
        drop_db(maint_url, temp_db_name)


def _alembic_ini() -> Path:
    """健壮地定位 alembic.ini 文件。"""
    # 从此文件开始向上查找包含 alembic.ini 的目录
    current = Path(__file__).resolve()
    while not (current / "alembic.ini").exists():
        if current.parent == current: # Reached the filesystem root
            pytest.fail("无法在任何父目录中找到 alembic.ini")
        current = current.parent
    
    ini_path = current / "alembic.ini"
    if not ini_path.is_file():
         pytest.fail(f"未找到 alembic.ini 在预期的位置: {ini_path}")
    return ini_path


def _cfg_safe(value: str) -> str:
    """为 configparser 安全地转义 '%' 符号。"""
    return value.replace("%", "%%")