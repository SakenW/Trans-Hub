# packages/server/alembic/env.py
"""
Alembic 环境配置 (v34 - 终极正确版)
- 在核心依赖升级后，恢复到最标准、最简洁的配置。
- 依赖 engine_from_config 来自动处理从上下文传入的配置。
"""
from __future__ import annotations
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, make_url

# --- 保证可导入项目 Base ---
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.infrastructure.db._schema import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """离线模式。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """在线模式。"""
    # 获取命令行参数中的数据库URL
    x_args = context.get_x_argument(as_dictionary=True)
    db_url = x_args.get('db_url')
    
    # 从配置文件获取section
    config_section = config.get_section(config.config_ini_section)
    
    # 如果提供了db_url参数，则覆盖配置中的url
    if db_url:
        config_section['sqlalchemy.url'] = db_url
    
    # 添加调试信息
    print("=== 调试信息 ===")
    print(f"配置section: {config_section}")
    print(f"数据库URL: {config_section.get('sqlalchemy.url')}")
    print("================")
    
    # [核心] connectable 直接从 config 对象的 section 中创建
    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
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