# packages/server/alembic/env.py
#
# TRANS-HUB v3.x 权威 Alembic 环境配置
#
# 特性：
# - 完全符合白皮书 v3.x 规范。
# - 智能路径解析，确保能从任何位置运行并导入项目 ORM Base。
# - 在线迁移前自动、幂等地创建 `th` schema。
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

# --- 路径设置 ---
# 将 `packages/server/src` 目录添加到 Python 路径，以便能导入 ORM Base
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

# 从 .ini 文件中解释日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置目标元数据，以便 autogenerate 可以检测到模型变化
target_metadata = Base.metadata

# --- Alembic 运行模式 ---


def run_migrations_offline() -> None:
    """在“离线”模式下运行迁移。

    这会配置上下文，只使用一个 URL 而不是 Engine，
    然后调用 context.run_migrations() 来生成 SQL 脚本。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,  # 保持一致
        version_table_schema="th",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在“在线”模式下运行迁移。

    在这种情况下，我们需要创建一个 Engine 并将其与一个 Connection 关联。
    然后将这个 Connection 传递给 context.configure()。
    """
    # 从 Alembic 上下文获取连接对象（由 CLI 传入）
    connectable = context.config.attributes.get("connection", None)

    if connectable is None:
        # 如果没有外部传入连接，则从 alembic.ini 创建
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    # 在事务中执行迁移
    with connectable.connect() as connection:
        # 1. [关键修复] 幂等地创建 'th' schema
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS th"))

        # 2. 配置 Alembic 上下文，使其知道我们的 schema
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 2a. [关键] 告诉 Alembic 我们要处理 schemas
            include_schemas=True,
            # 2b. [关键] 将 alembic_version 表放在 'th' schema 中
            version_table_schema="th",
            # 2c. [最佳实践] 启用对类型和默认值的比较
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# --- 主逻辑 ---
if context.is_offline_mode():
    logging.info("正在离线模式下运行迁移...")
    run_migrations_offline()
else:
    logging.info("正在在线模式下运行迁移...")
    run_migrations_online()
