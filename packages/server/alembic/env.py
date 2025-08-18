# packages/server/alembic/env.py
#
# TRANS-HUB v3.x 权威 Alembic 环境配置 (最终方言感知修复版)
#
# 特性：
# - [关键修复] 增加方言检查，确保 CREATE SCHEMA/TYPE 等 PG 专属命令只在 PostgreSQL 环境下执行。
# - 移除所有自引导配置加载逻辑，完全信任从 Alembic Config 传入的 `sqlalchemy.url`。
# - 使用正确的 SQLAlchemy API 在 `connection` 对象上执行 AUTOCOMMIT DDL。
# - `target_metadata` 在在线模式下设为 None，确保迁移脚本的纯粹执行。
#
from __future__ import annotations

import logging
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# --- 路径设置 ---
try:
    SRC_DIR = Path(__file__).resolve().parents[2] / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from trans_hub.infrastructure.db._schema import Base
except (ImportError, IndexError) as e:
    sys.stderr.write(
        f"错误: 无法找到或导入 ORM Base 元数据。请确保 'src' 目录结构正确。\n"
        f"  - 查找路径: {SRC_DIR}\n"
        f"  - 错误: {e}\n"
    )
    sys.exit(1)


# --- Alembic 配置 ---
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# [关键修复] 对于 SQLite，SQLAlchemy 会自动处理 schema 前缀，这里保持 th
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
        # [关键修复] Alembic 在 SQLite 下会自动将 schema 作为表名前缀
        version_table_schema="th",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在“在线”模式下运行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # [关键修复] 只有当数据库是 PostgreSQL 时，才执行 PG 专属的初始化命令
        if connection.dialect.name == "postgresql":
            autocommit_connection = connection.execution_options(isolation_level="AUTOCOMMIT")
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
            target_metadata=None, # 确保 Alembic 只执行迁移脚本
            include_schemas=True, # 告诉 Alembic 要考虑 schema
            version_table_schema="th",
            compare_type=True,
            compare_server_default=True,
        )

        # 在事务中运行迁移脚本
        with context.begin_transaction():
            context.run_migrations()

# --- 主逻辑 ---
if context.is_offline_mode():
    logging.info("正在离线模式下运行迁移...")
    run_migrations_offline()
else:
    logging.info("正在在线模式下运行迁移...")
    run_migrations_online()