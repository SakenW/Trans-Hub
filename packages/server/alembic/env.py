# packages/server/alembic/env.py
"""
Alembic 的环境配置文件。
这个文件在运行 `alembic` 命令时被调用。
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url

from alembic import context

# --- 路径设置 ---
# 将项目的 src 目录添加到 Python 路径中，以便 Alembic 能找到我们的 ORM 模型
# (这个脚本在 alembic/ 目录下，src 在上一级的 src/ 目录中)
project_root = Path(__file__).resolve().parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from trans_hub.config import TransHubConfig
from trans_hub.infrastructure.db._schema import Base

# --- Alembic 配置加载 ---
config = context.config

# 从 .ini 文件中解释日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置元数据以支持 autogenerate
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """在“离线”模式下运行迁移。"""
    # 优先使用 alembic.ini 中的 sqlalchemy.url，否则从我们的应用配置中加载
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
    # 从配置中获取数据库 URL
    app_db_url_str = (
        config.get_main_option("sqlalchemy.url") or TransHubConfig().database_url
    )
    
    url = make_url(app_db_url_str)

    # [核心修复] 如果 URL 是异步的，将其转换为同步版本以供 Alembic 使用
    if url.drivername.endswith(("+asyncpg", "+aiosqlite", "+psycopg")):
        sync_drivername = url.drivername.split("+")[0]
        # 对于 psycopg3，需要特别指定 psycopg2 方言
        if sync_drivername == "postgresql":
             sync_drivername = "postgresql+psycopg2"
        
        # 创建一个新的同步 URL
        url = url._replace(drivername=sync_drivername)

    connectable = create_engine(str(url))

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()