# packages/server/alembic/env.py
"""
Alembic 环境配置（修复版）
要点：
- 仅在日志里脱敏打印；实际连接始终使用未脱敏 URL。
- 若 URL 为异步驱动（+asyncpg / +psycopg 等），自动转换为 postgresql+psycopg2。
- 在线模式使用 NullPool，减少测试/工具阶段连接占用。
- 不在 configure() 之前访问 context.get_context()，避免 "No context has been configured yet"。
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Optional

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import make_url, URL

# --- 保证可导入项目 Base ---
SRC_DIR = Path(__file__).resolve().parents[2] / "src"  # packages/server/src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.infrastructure.db._schema import Base  # noqa: E402

# 读取 Alembic 的配置对象
config = context.config

# 如果 alembic.ini 启用了日志配置，则设定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据（用于自动生成迁移）
target_metadata = Base.metadata


def _raw_sqlalchemy_url() -> str:
    """
    返回未脱敏的 sqlalchemy.url（供真实连接使用）。
    优先 alembic.ini 的 sqlalchemy.url；否则读取环境变量 TH_DATABASE_URL / DATABASE_URL。
    """
    url = (config.get_main_option("sqlalchemy.url") or "").strip()
    if not url:
        env_url = os.getenv("TH_DATABASE_URL") or os.getenv("DATABASE_URL")
        if env_url:
            url = env_url.strip()
    if not url:
        raise RuntimeError("Alembic 未获得 sqlalchemy.url，请在 alembic.ini 或环境变量中提供。")
    return url


def _mask_url(url_str: str) -> str:
    try:
        return make_url(url_str).render_as_string(hide_password=True)
    except Exception:
        return url_str


def _to_sync_psycopg2(url_str: str) -> str:
    """
    若 URL 是异步驱动或 psycopg3，转换为 postgresql+psycopg2。
    对于已经是 postgresql+psycopg2 或其他同步驱动，原样返回。
    """
    u = make_url(url_str)
    driver = u.drivername or "postgresql"
    # 常见异步/新驱动标识
    if driver.endswith("+asyncpg") or driver.endswith("+psycopg") or driver == "postgresql":
        # 统一转 psycopg2；若已是 postgresql+psycopg2 则不会改变
        u = u.set(drivername="postgresql+psycopg2")
    return str(u)


def run_migrations_offline() -> None:
    """离线模式：不连接数据库，仅生成 SQL。"""
    url_raw = _raw_sqlalchemy_url()
    url_sync = _to_sync_psycopg2(url_raw)

    # 仅打印：脱敏
    print(f"[alembic][offline] sqlalchemy.url = {_mask_url(url_sync)}")

    context.configure(
        url=url_sync,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：实际连接数据库并执行迁移。"""
    url_raw = _raw_sqlalchemy_url()
    url_sync = _to_sync_psycopg2(url_raw)

    # 仅打印：脱敏
    print(f"[alembic][online] sqlalchemy.url = {_mask_url(url_sync)}")

    # 将未脱敏、已转换为 psycopg2 的 URL 写回给 engine_from_config 使用
    ini_section = config.get_section(config.config_ini_section) or {}
    ini_section["sqlalchemy.url"] = url_sync

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # 测试/工具期建议 NullPool，减少连接占用
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
