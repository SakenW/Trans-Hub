# alembic/env.py (最终修正版，采用 nest_asyncio)

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

# --- [核心修复] 引入并应用 nest_asyncio ---
# 必须在所有 asyncio 操作之前执行
import nest_asyncio
nest_asyncio.apply()
# -----------------------------------------

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# --- 路径设置 ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from trans_hub.config import TransHubConfig
from trans_hub.db.schema import Base

# --- Alembic 配置加载 ---
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """在“离线”模式下运行迁移。"""
    url = config.get_main_option("sqlalchemy.url") or TransHubConfig().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """迁移执行的核心逻辑。"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """核心的异步迁移函数。"""
    db_url = config.get_main_option("sqlalchemy.url") or TransHubConfig().database_url
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # [最终方案] 由于 nest_asyncio.apply() 的存在，
    # 无论外部是否有正在运行的事件循环，
    # asyncio.run() 现在都能安全、正确地工作。
    asyncio.run(run_async_migrations())