# alembic/env.py (最终同步版)

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url # <-- [核心修复] 导入 SQLAlchemy 的 URL 解析器

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
    # 从配置中获取应用的数据库URL
    app_db_url_str = config.get_main_option("sqlalchemy.url") or TransHubConfig().database_url
    
    # [核心修复] 为 Alembic 创建一个纯同步的连接URL。
    # Alembic 作为一个管理工具，必须使用同步驱动。
    url = make_url(app_db_url_str)
    
    if url.drivername.endswith(("+asyncpg", "+aiosqlite")):
        # 将 'postgresql+asyncpg' 变为 'postgresql'
        # 将 'sqlite+aiosqlite' 变为 'sqlite'
        url = url.set(drivername=url.drivername.split("+")[0])
    
    sync_db_url = url.render_as_string(hide_password=False)
        
    connectable = create_engine(sync_db_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()