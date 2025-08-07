# alembic/env.py
# Alembic 迁移环境的配置文件。
# 这是 Alembic 的核心，负责连接数据库、加载模型定义并执行迁移。

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# --- [核心修改] 将项目根目录添加到 Python 路径中 ---
# 这使得 Alembic 环境可以导入 Trans-Hub 的模块。
current_dir = Path(__file__).parent.parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

# --- [核心修改] 导入我们的模型和配置 ---
from trans_hub.config import TransHubConfig  # noqa: E402
from trans_hub.db.schema import Base         # noqa: E402

# 从 alembic.ini 加载日志配置。
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- [核心修改] 设置目标元数据 ---
# `target_metadata` 指向我们用 SQLAlchemy 定义的所有数据模型的元数据。
# Alembic 将会把数据库的当前状态与这个元数据进行比较，以自动生成迁移。
target_metadata = Base.metadata

# 从我们的 TransHubConfig 获取数据库 URL，而不是硬编码。
# 如果 .env 文件中没有设置，它会使用默认的 sqlite:///transhub.db
db_config = TransHubConfig()
config.set_main_option("sqlalchemy.url", db_config.database_url)


def run_migrations_offline() -> None:
    """在“离线”模式下运行迁移。
    这会生成 SQL 脚本，但不会直接连接数据库执行。
    """
    url = config.get_main_option("sqlalchemy.url")
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


async def run_migrations_online() -> None:
    """在“在线”模式下运行迁移。
    这会创建数据库连接并直接应用迁移。
    这是我们主要使用的模式。
    """
    # [核心修改] 创建一个支持异步的 SQLAlchemy 引擎。
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # [核心修改] 使用 run_sync 方法来桥接异步连接和同步的 Alembic 上下文。
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # [核心修改] 使用 asyncio.run 来执行异步的在线迁移。
    asyncio.run(run_migrations_online())