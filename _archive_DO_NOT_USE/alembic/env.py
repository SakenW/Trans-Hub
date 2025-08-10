# alembic/env.py

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

from alembic import context

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


def run_migrations_online() -> None:
    """在“在线”模式下运行迁移。"""
    app_db_url_str = (
        config.get_main_option("sqlalchemy.url") or TransHubConfig().database_url
    )

    url = make_url(app_db_url_str)

    # [核心修复] 使用公共属性构建新的 URL，而不是调用 mypy 无法验证的方法
    if url.drivername.endswith(("+asyncpg", "+aiosqlite")):
        sync_drivername = url.drivername.split("+")[0]
        # 创建一个新的 URL 对象
        url = url._replace(drivername=sync_drivername)

    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
