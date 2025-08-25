# packages/server/alembic/env.py
"""
Alembic 环境配置 (v3.0 - 最终修复版)

此版本解决了测试和生产迁移中的 schema 问题，确保行为一致：

1.  **元数据来源**: 优先使用从 `context.config.attributes` 注入的 `target_metadata`。
    这允许 `tests/conftest.py` 在测试时提供与应用完全一致的元数据对象。
    如果未注入，则回退到从 `trans_hub.infrastructure.db._schema` 标准导入，
    以支持 `alembic` 命令行工具的直接使用。

2.  **统一的 Schema 配置**: [关键修复] 无论元数据来自注入还是导入，
    本脚本都会从 `alembic.ini` 读取 `db_schema` 配置，并将其统一应用到
    `target_metadata.schema` 属性上。这确保了 Alembic 的迁移操作
    (包括 `alembic_version` 表的创建) 始终在正确的、预期的 schema 中执行，
    从而根除了 `schema "th" does not exist` 的错误。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

import structlog
from alembic import context
from sqlalchemy import pool, text

# 获取 structlog logger
logger = structlog.get_logger(__name__)

# --- 路径设置 ---
# 将 `src` 目录添加到 sys.path，以允许 `trans_hub` 模块的绝对导入。
try:
    SRC_DIR = Path(__file__).resolve().parents[2] / "src"
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
except IndexError:
    sys.stderr.write(f"错误: 无法从路径 {__file__} 推断出 'src' 目录。\n")
    sys.exit(1)

# --- Alembic 配置 ---
config = context.config

# 为日志记录解释配置文件。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- 元数据处理 ---
# 步骤 1: 获取元数据对象，优先从测试注入，否则从业务代码导入。
target_metadata = config.attributes.get("target_metadata")
if target_metadata is None:
    # 此代码块在通过命令行运行 `alembic` 时执行
    try:
        from trans_hub.infrastructure.db._schema import Base

        target_metadata = Base.metadata
    except ImportError as e:
        sys.stderr.write(
            f"错误: 无法导入 SQLAlchemy Base 模型。请确保 PYTHONPATH 正确。\n"
            f"  - 详情: {e}\n"
        )
        sys.exit(1)

# 步骤 2: [关键修复] 统一应用 schema。无论元数据来自何处，
# 默认的数据库 schema 名称配置
db_schema = config.get_main_option("db_schema", None)
if db_schema and db_schema != "None":
    # 获取数据库 schema 配置并设置 target_metadata.schema
    sqlalchemy_url = config.get_main_option("sqlalchemy.url", "")

    # 检查是否有注入的引擎（用于测试）
    injected_engine = config.attributes.get("connection")
    if injected_engine is not None:
        is_postgresql = injected_engine.dialect.name == "postgresql"
        logger.debug("从注入引擎检测到方言", dialect=injected_engine.dialect.name)
    else:
        # 如果没有注入引擎且没有URL配置，尝试从应用配置检测
        if not sqlalchemy_url:
            try:
                from trans_hub.bootstrap.init import create_app_config

                app_config = create_app_config("test")
                db_url = str(app_config.database.url)
                is_postgresql = "postgresql" in db_url
                logger.debug(
                    "从应用配置检测到方言",
                    dialect="postgresql" if is_postgresql else "other",
                )
            except Exception:
                is_postgresql = False
                logger.debug("无法检测方言，默认为非PostgreSQL")
        else:
            is_postgresql = sqlalchemy_url.startswith("postgresql")
            logger.debug(
                "从URL检测到方言", dialect="postgresql" if is_postgresql else "other"
            )

    if is_postgresql:
        target_metadata.schema = db_schema
        logger.debug("设置 target_metadata.schema", schema=db_schema)
    else:
        target_metadata.schema = None
        logger.debug("非 PostgreSQL，设置 target_metadata.schema = None")
else:
    target_metadata.schema = None
    logger.debug("无 db_schema 配置，设置 target_metadata.schema = None")


def run_migrations_offline() -> None:
    """在"离线"模式下运行迁移。"""
    url = config.get_main_option("sqlalchemy.url")

    # 如果没有配置URL，尝试从应用配置获取
    if not url:
        try:
            from trans_hub.bootstrap.init import create_app_config

            app_config = create_app_config("test")

            # 将异步URL转换为同步URL（离线模式需要同步URL）
            db_url = str(app_config.database.url)
            if "+asyncpg://" in db_url:
                url = db_url.replace("+asyncpg://", "+psycopg://")
            elif "+aiosqlite://" in db_url:
                url = db_url.replace("+aiosqlite://", "://")
            else:
                url = db_url
            logger.debug("离线模式使用应用配置URL", url=url)
        except Exception as e:
            logger.error("离线模式无法获取数据库URL", error=str(e))
            raise RuntimeError(
                "离线模式需要数据库URL配置。请确保：\n"
                "1. alembic.ini中配置了sqlalchemy.url\n"
                "2. 或者环境变量已正确配置\n"
                f"错误详情: {e}"
            ) from e

    # 版本表与业务表在同一 schema 中
    version_table_schema = target_metadata.schema
    logger.debug("离线迁移 - version_table_schema", schema=version_table_schema)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=version_table_schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在"在线"模式下运行迁移。"""
    # [关键修复] 优先使用从测试传入的引擎连接
    # 这确保迁移和应用使用完全相同的数据库连接
    injected_engine = config.attributes.get("connection")
    if injected_engine is not None:
        logger.debug("使用注入的引擎连接", url=str(injected_engine.engine.url))
        connectable = injected_engine
    else:
        # 当没有注入引擎时，按优先级获取数据库连接：
        # 1. Alembic配置中的sqlalchemy.url（最高优先级）
        # 2. 环境变量TRANSHUB_DATABASE_URL
        # 3. 应用配置（最低优先级）
        logger.debug("没有注入引擎，尝试获取数据库连接")

        # 首先检查Alembic配置中的sqlalchemy.url
        alembic_url = config.get_main_option("sqlalchemy.url")
        if alembic_url and alembic_url.strip():
            logger.debug("使用Alembic配置中的数据库URL", url=alembic_url)
            from sqlalchemy import create_engine

            connectable = create_engine(
                alembic_url,
                poolclass=pool.NullPool,
            )
            logger.debug("使用Alembic配置创建引擎", url=str(connectable.url))
        else:
            # 检查是否有环境变量设置的数据库URL
            env_db_url = os.environ.get("TRANSHUB_DATABASE_URL")
            if env_db_url:
                logger.debug("使用环境变量数据库URL", url=env_db_url)
                # 将异步URL转换为同步URL（Alembic需要同步连接）
                if "+asyncpg://" in env_db_url:
                    sync_db_url = env_db_url.replace("+asyncpg://", "+psycopg://")
                elif "+aiosqlite://" in env_db_url:
                    sync_db_url = env_db_url.replace("+aiosqlite://", "://")
                else:
                    sync_db_url = env_db_url

                from sqlalchemy import create_engine

                connectable = create_engine(
                    sync_db_url,
                    poolclass=pool.NullPool,
                )
                logger.debug("使用环境变量创建引擎", url=str(connectable.url))
            else:
                # 回退到应用配置
                logger.debug("环境变量未设置，回退到应用配置")
                try:
                    from trans_hub.bootstrap.init import create_app_config

                    # 使用测试环境模式加载配置
                    app_config = create_app_config("test")

                    # 使用应用配置创建引擎
                    from sqlalchemy import create_engine

                    # 将异步URL转换为同步URL（Alembic需要同步连接）
                    db_url = str(app_config.database.url)
                    if "+asyncpg://" in db_url:
                        sync_db_url = db_url.replace("+asyncpg://", "+psycopg://")
                    elif "+aiosqlite://" in db_url:
                        sync_db_url = db_url.replace("+aiosqlite://", "://")
                    else:
                        sync_db_url = db_url

                    connectable = create_engine(
                        sync_db_url,
                        poolclass=pool.NullPool,
                    )
                    logger.debug("使用应用配置创建引擎", url=str(connectable.url))
                except Exception as e:
                    logger.error("无法从应用配置获取数据库连接", error=str(e))
                    raise RuntimeError(
                        "无法获取数据库连接。请确保：\n"
                        "1. 环境变量已正确配置\n"
                        "2. 或者通过代码注入数据库连接\n"
                        f"错误详情: {e}"
                    ) from e

    # 根据connectable的类型决定如何获取连接
    if hasattr(connectable, "connect"):
        # 这是一个Engine对象，需要调用connect()
        connection_context = connectable.connect()
    else:
        # 这是一个Connection对象，直接使用
        from contextlib import nullcontext

        connection_context = nullcontext(connectable)

    with connection_context as connection:
        logger.debug("在线迁移 - target_metadata.schema", schema=target_metadata.schema)
        logger.debug("在线迁移 - 表数量", count=len(target_metadata.tables))
        for table_name, table in target_metadata.tables.items():
            logger.debug("表信息", table_name=table_name, schema=table.schema)

        # [关键修复] 在配置context之前，确保目标schema存在
        # 这解决了Alembic试图在不存在的schema中创建alembic_version表的问题
        if target_metadata.schema and connection.dialect.name == "postgresql":
            logger.debug("确保schema存在", schema=target_metadata.schema)
            connection.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {target_metadata.schema}")
            )
            # 注意：不在这里提交，因为连接可能已经在事务中

        # 版本表与业务表在同一 schema 中
        version_table_schema = target_metadata.schema
        logger.debug("配置 version_table_schema", schema=version_table_schema)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=version_table_schema,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
