# packages/server/alembic/env.py
# 
# TRANS-HUB v3.x 权威 Alembic 环境配置 (最终修正版)
# 
# 特性：
# - [最终修复] 修正 SQLAlchemy API 调用，直接在配置了 AUTOCOMMIT 的连接上执行 DDL。
# - 在主迁移事务开始前，以 AUTOCOMMIT 模式创建 schema 和自定义 ENUM 类型。
# - 完全符合白皮书 v3.x 规范。
# - 智能路径解析，确保能从任何位置运行并导入项目 ORM Base。
# - 启用 `include_schemas=True` 和 `version_table_schema="th"`，正确处理 PostgreSQL schema。
# - 启用 `compare_type` 和 `compare_server_default` 以获得更精确的 autogenerate。
# - 使用标准 logging，输出清晰，易于调试。
#
from __future__ import annotations

import logging
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# --- 路径与配置加载 ---
try:
    SRC_DIR = Path(__file__).resolve().parents[2] / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    
    # [v3.0.0] 不再需要 bootstrap，Alembic 自身通过 alembic.ini + 环境变量加载
    from trans_hub.infrastructure.db._schema import Base

except (ImportError, IndexError, RuntimeError) as e:
    sys.stderr.write(
        f"错误: 无法加载 ORM Base 元数据。\n"
        f"  - 查找路径: {SRC_DIR}\n"
        f"  - 错误: {e}\n"
    )
    sys.exit(1)


# --- Alembic 配置 ---
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# --- Alembic 运行模式 ---


def run_migrations_offline() -> None:
    """在“离线”模式下运行迁移。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="th",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在“在线”模式下运行迁移。"""
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        # [最终修复] 修正 API 调用方式。
        # 直接在配置了 execution_options 的 connection 上执行，而不是在 transaction 对象上。
        autocommit_connection = connection.execution_options(
            isolation_level="AUTOCOMMIT"
        )
        autocommit_connection.execute(text("CREATE SCHEMA IF NOT EXISTS th"))
        autocommit_connection.execute(
            text(
                """
                DO $$ BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='translation_status' AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'th')) THEN 
                        CREATE TYPE th.translation_status AS ENUM ('draft','reviewed','published','rejected'); 
                    END IF; 
                END $$; 
                """
            )
        )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="th",
            compare_type=True,
            compare_server_default=True,
        )

        # Alembic 的迁移脚本本身在一个事务中运行
        with context.begin_transaction():
            context.run_migrations()


# --- 主逻辑 ---
if context.is_offline_mode():
    logging.info("正在离线模式下运行迁移...")
    run_migrations_offline()
else:
    logging.info("正在在线模式下运行迁移...")
    run_migrations_online()
