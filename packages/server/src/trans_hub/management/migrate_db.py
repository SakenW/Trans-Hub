# trans_hub/management/migrate_db.py
"""数据库迁移管理脚本

这个脚本解决了 Alembic 在使用自定义 schema 时的版本表位置问题。
通过确保 alembic_version 表在 public schema 中，而业务表在指定的 schema 中。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# 添加 src 目录到 Python 路径
SRC_DIR = Path(__file__).parent.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.bootstrap.init import load_config_with_validation
from trans_hub.infrastructure.db._schema import Base
from trans_hub.management.config_utils import get_real_db_url, convert_async_to_sync_url


def ensure_alembic_version_table(engine: Engine) -> None:
    """确保 alembic_version 表在 public schema 中存在"""
    with engine.connect() as connection:
        if engine.dialect.name == 'postgresql':
            # PostgreSQL: 检查 alembic_version 表是否已存在于 public schema
            result = connection.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_name = 'alembic_version' AND table_schema = 'public'
            """))
            
            if not result.fetchone():
                # 创建 alembic_version 表在 public schema
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS public.alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                """))
                connection.commit()
                print("✅ alembic_version 表在 public schema 中创建成功")
            else:
                print("ℹ️  alembic_version 表已存在于 public schema 中")
        elif engine.dialect.name == 'sqlite':
            # SQLite: 检查 alembic_version 表是否存在
            result = connection.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='alembic_version'
            """))
            
            if not result.fetchone():
                # 创建 alembic_version 表
                connection.execute(text("""
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(32) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                """))
                connection.commit()
                print("✅ alembic_version 表创建成功")
            else:
                print("ℹ️  alembic_version 表已存在")
        else:
            print(f"⚠️  未知数据库类型 '{engine.dialect.name}'，跳过版本表检查")


def ensure_target_schema(engine: Engine, schema_name: str) -> None:
    """确保目标 schema 存在"""
    with engine.connect() as connection:
        # 检查数据库类型
        if engine.dialect.name == 'postgresql':
            # PostgreSQL: 检查 schema 是否存在
            result = connection.execute(text(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"
            ), {"schema": schema_name})
            
            if not result.fetchone():
                # 创建 schema
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
                connection.commit()
                print(f"✅ Schema '{schema_name}' 创建成功")
            else:
                print(f"ℹ️  Schema '{schema_name}' 已存在")
        elif engine.dialect.name == 'sqlite':
            # SQLite 不支持 schema，跳过
            print(f"ℹ️  SQLite 数据库不支持 schema，跳过 schema '{schema_name}' 的创建")
        else:
            print(f"⚠️  未知数据库类型 '{engine.dialect.name}'，跳过 schema 创建")


def patch_alembic_context() -> tuple[Any, Any]:
    """通过猴子补丁修改 Alembic context.configure 来强制版本表在 public schema
    
    Returns:
        tuple: (original_configure, patched_configure) 用于后续恢复
    """
    from alembic import context
    
    # 保存原始的 configure 函数
    original_configure = context.configure
    
    def patched_configure(*args: Any, **kwargs: Any) -> Any:
        """修改后的 configure 函数，强制 version_table_schema 为 None"""
        # 强制设置 version_table_schema 为 None，确保版本表在 public schema
        kwargs['version_table_schema'] = None
        return original_configure(*args, **kwargs)
    
    # 临时替换 context.configure
    context.configure = patched_configure
    
    return original_configure, patched_configure


def restore_alembic_context(original_configure: Any) -> None:
    """恢复原始的 Alembic context.configure 函数"""
    from alembic import context
    context.configure = original_configure


def run_migration(target_revision: str = "head", schema_name: str = "th") -> None:
    """执行数据库迁移
    
    Args:
        target_revision: 目标迁移版本，默认为 "head"
        schema_name: 目标 schema 名称，默认为 "th"
    """
    print(f"开始数据库迁移到版本: {target_revision}")
    print(f"目标 schema: {schema_name}")
    
    # 1. 加载配置
    config = load_config_with_validation("prod")
    db_url = get_real_db_url(config.database.url)
    
    # 2. 创建同步引擎
    sync_url = convert_async_to_sync_url(db_url)
    engine = create_engine(sync_url)
    
    print(f"数据库连接: {sync_url}")
    
    try:
        # 3. 确保目标 schema 存在
        ensure_target_schema(engine, schema_name)
        
        # 4. 确保 alembic_version 表在 public schema 中存在
        ensure_alembic_version_table(engine)
        
        # 5. 配置 Alembic
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
        alembic_cfg.set_main_option("db_schema", schema_name)
        
        # 设置 metadata schema
        Base.metadata.schema = schema_name
        alembic_cfg.attributes["target_metadata"] = Base.metadata
        
        print("✅ Alembic 配置完成")
        
        # 6. 应用猴子补丁并执行迁移
        original_configure, _ = patch_alembic_context()
        
        try:
            print(f"执行迁移到版本: {target_revision}")
            command.upgrade(alembic_cfg, target_revision)
            print("✅ 迁移执行成功")
        finally:
            # 恢复原始的 configure 函数
            restore_alembic_context(original_configure)
            
    except Exception as e:
        print(f"❌ 迁移执行失败: {e}")
        raise
    finally:
        engine.dispose()


def downgrade_migration(target_revision: str, schema_name: str = "th") -> None:
    """回滚数据库迁移
    
    Args:
        target_revision: 目标迁移版本
        schema_name: 目标 schema 名称，默认为 "th"
    """
    print(f"开始数据库回滚到版本: {target_revision}")
    print(f"目标 schema: {schema_name}")
    
    # 1. 加载配置
    config = load_config_with_validation("prod")
    db_url = get_real_db_url(config.database.url)
    
    # 2. 创建同步引擎
    sync_url = convert_async_to_sync_url(db_url)
    engine = create_engine(sync_url)
    
    print(f"数据库连接: {sync_url}")
    
    try:
        # 3. 配置 Alembic
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
        alembic_cfg.set_main_option("db_schema", schema_name)
        
        # 设置 metadata schema
        Base.metadata.schema = schema_name
        alembic_cfg.attributes["target_metadata"] = Base.metadata
        
        print("✅ Alembic 配置完成")
        
        # 4. 应用猴子补丁并执行回滚
        original_configure, _ = patch_alembic_context()
        
        try:
            print(f"执行回滚到版本: {target_revision}")
            command.downgrade(alembic_cfg, target_revision)
            print("✅ 回滚执行成功")
        finally:
            # 恢复原始的 configure 函数
            restore_alembic_context(original_configure)
            
    except Exception as e:
        print(f"❌ 回滚执行失败: {e}")
        raise
    finally:
        engine.dispose()


def show_migration_history(schema_name: str = "th") -> None:
    """显示迁移历史
    
    Args:
        schema_name: 目标 schema 名称，默认为 "th"
    """
    # 1. 加载配置
    config = load_config_with_validation("prod")
    db_url = get_real_db_url(config.database.url)
    
    # 2. 创建同步引擎
    sync_url = convert_async_to_sync_url(db_url)
    
    # 3. 配置 Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    alembic_cfg.set_main_option("db_schema", schema_name)
    
    # 设置 metadata schema
    Base.metadata.schema = schema_name
    alembic_cfg.attributes["target_metadata"] = Base.metadata
    
    try:
        # 4. 应用猴子补丁并显示历史
        original_configure, _ = patch_alembic_context()
        
        try:
            print("当前迁移状态:")
            command.current(alembic_cfg)
            print("\n迁移历史:")
            command.history(alembic_cfg)
        finally:
            # 恢复原始的 configure 函数
            restore_alembic_context(original_configure)
            
    except Exception as e:
        print(f"❌ 获取迁移历史失败: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移管理")
    parser.add_argument("command", choices=["upgrade", "downgrade", "history"], 
                       help="迁移命令")
    parser.add_argument("--revision", "-r", default="head", 
                       help="目标迁移版本 (默认: head)")
    parser.add_argument("--schema", "-s", default="th", 
                       help="目标 schema 名称 (默认: th)")
    
    args = parser.parse_args()
    
    if args.command == "upgrade":
        run_migration(args.revision, args.schema)
    elif args.command == "downgrade":
        if args.revision == "head":
            print("错误: 回滚操作必须指定具体的版本号")
            sys.exit(1)
        downgrade_migration(args.revision, args.schema)
    elif args.command == "history":
        show_migration_history(args.schema)