# packages/server/alembic/env.py
"""
Alembic 环境配置 (v35 - 日志规范化版)
- 移除了所有调试用的 print 语句。
- 使用标准 logging 模块输出关键信息，以便与项目日志系统集成。
"""
from __future__ import annotations
import sys
import logging
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- 日志配置 ---
# 获取一个标准的 logger 实例
log = logging.getLogger(__name__)

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
    log.info(f"以离线模式运行迁移，目标 URL: {url}")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
    log.info("离线迁移完成。")

def run_migrations_online() -> None:
    """在线模式。"""
    # [核心] connectable 直接从 config 对象的 section 中创建
    # 这种方式允许 pytest fixture 通过 alembic.context 传递连接信息
    connectable = context.config.attributes.get("connection", None)
    
    if connectable is None:
        log.info("未从上下文获取到连接，将从 alembic.ini 创建引擎。")
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    log.info(f"以在线模式运行迁移，连接: {connectable.engine}")

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    log.info("在线迁移完成。")

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()