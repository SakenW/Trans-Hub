#!/usr/bin/env python3
# test_postgresql_migration.py
"""
测试PostgreSQL环境下的迁移执行
"""

import asyncio
import sys
from pathlib import Path

# 添加src目录到路径
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from trans_hub.bootstrap.init import load_config_with_validation
from tests.helpers.tools.db_manager import managed_temp_database
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, text
from alembic.config import Config
from trans_hub.management.config_utils import get_real_db_url


def run_migrations(engine, db_schema: str | None):
    """执行Alembic迁移"""
    from alembic import command
    
    alembic_ini_path = Path(__file__).parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    
    # 设置数据库URL
    sync_dsn = engine.url.render_as_string(hide_password=False)
    alembic_cfg.set_main_option("sqlalchemy.url", sync_dsn)
    
    if db_schema:
        alembic_cfg.set_main_option("db_schema", db_schema)
    
    print(f"执行迁移到数据库: {sync_dsn}")
    print(f"使用schema: {db_schema}")
    
    # 执行迁移
    command.upgrade(alembic_cfg, "head")
    print("迁移执行完成")


def test_postgresql_migration():
    """测试PostgreSQL环境下的迁移"""
    print("=== PostgreSQL迁移测试 ===")
    
    # 加载测试配置
    config = load_config_with_validation("test")
    print(f"数据库URL: {config.database.url}")
    print(f"维护库URL: {config.maintenance_database_url}")
    
    # 获取维护库URL
    raw_maint_dsn = config.maintenance_database_url
    if not raw_maint_dsn:
        print("错误: 维护库DSN未配置")
        return
    
    real_maint_dsn = get_real_db_url(raw_maint_dsn)
    maint_url = make_url(real_maint_dsn)
    
    print(f"使用维护库: {maint_url}")
    
    # 生成固定的临时数据库名称
    import uuid
    temp_db_name = f"th_test_{uuid.uuid4().hex[:8]}"
    print(f"生成临时数据库名称: {temp_db_name}")
    
    # 手动构建临时数据库URL
    temp_db_url = maint_url.set(database=temp_db_name)
    print(f"临时数据库URL: {temp_db_url}")
    
    # 创建临时数据库
    maintenance_engine = create_engine(
        config.maintenance_database_url.replace("+asyncpg", "+psycopg"),
        isolation_level="AUTOCOMMIT"  # 设置自动提交模式
    )
    
    try:
        # 创建数据库
        with maintenance_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {temp_db_name}"))
            print(f"成功创建临时数据库: {temp_db_name}")
        
        # 创建同步引擎用于迁移
        sync_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+asyncpg", "+psycopg"
        )
        sync_engine = create_engine(
            sync_dsn,
            isolation_level="AUTOCOMMIT"  # 设置自动提交模式避免事务问题
        )
        
        print(f"同步引擎DSN: {sync_dsn}")
        
        # 执行迁移
        try:
            print("开始执行迁移...")
            print(f"[DEBUG] 设置Alembic使用数据库: {sync_dsn}")
            
            from alembic import command
            alembic_cfg = Config("alembic.ini")
            alembic_cfg.set_main_option("sqlalchemy.url", sync_dsn)
            print(f"[DEBUG] Alembic配置中的URL: {alembic_cfg.get_main_option('sqlalchemy.url')}")
            
            # 创建一个专门用于迁移的引擎，不使用AUTOCOMMIT模式
            migration_engine = create_engine(sync_dsn)
            
            try:
                # 使用连接注入的方式执行迁移
                with migration_engine.connect() as conn:
                    # 将连接注入到Alembic配置中
                    alembic_cfg.attributes['connection'] = conn
                    
                    # 开始事务并执行迁移
                    with conn.begin():
                        command.upgrade(alembic_cfg, "head")
                        print("迁移执行完成，事务已提交")
                
            except Exception as e:
                print(f"迁移执行失败: {e}")
                raise
            finally:
                migration_engine.dispose()
            
            # 立即检查迁移后的状态
            print("\n=== 迁移后立即检查 ===")
            temp_check_engine = create_engine(
                sync_dsn,
                isolation_level="AUTOCOMMIT"
            )
            try:
                with temp_check_engine.connect() as conn:
                    # 检查是否有任何表被创建
                    result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.tables 
                        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                        ORDER BY table_schema, table_name
                    """))
                    immediate_tables = [(row[0], row[1]) for row in result]
                    print(f"迁移后立即发现的表: {immediate_tables}")
                    
                    # 检查是否有schema被创建
                    result = conn.execute(text("""
                        SELECT schema_name 
                        FROM information_schema.schemata 
                        WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                    """))
                    immediate_schemas = [row[0] for row in result]
                    print(f"迁移后立即发现的schema: {immediate_schemas}")
            finally:
                temp_check_engine.dispose()
            print("=== 迁移后立即检查完成 ===\n")
            
            # 重要：确保迁移事务已提交，重新创建引擎连接
            sync_engine.dispose()
            sync_engine = create_engine(sync_dsn)
            
            # 检查迁移后的表
            print(f"[DEBUG] 验证时使用的数据库引擎: {sync_engine.url}")
            
            # 验证迁移结果 - 为每个查询使用独立连接避免事务问题
            print(f"[DEBUG] 验证连接建立成功")
            
            # 首先检查Alembic版本表
            try:
                with sync_engine.connect() as conn:
                    result = conn.execute(text("SELECT version_num FROM th.alembic_version"))
                    version = result.scalar()
                    print(f"Alembic版本表存在，当前版本: {version}")
            except Exception as e:
                print(f"Alembic版本表不存在: {e}")
                
                # 尝试检查public schema中的版本表
                try:
                    with sync_engine.connect() as conn:
                        result = conn.execute(text("SELECT version_num FROM alembic_version"))
                        version = result.scalar()
                        print(f"Public schema中的Alembic版本表存在，当前版本: {version}")
                except Exception as e2:
                    print(f"Public schema中的Alembic版本表也不存在: {e2}")
            
            # 检查schema
            try:
                with sync_engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT schema_name 
                        FROM information_schema.schemata 
                        WHERE schema_name = 'th'
                    """))
                    schemas = [row[0] for row in result]
                    print(f"找到schema: {schemas}")
            except Exception as e:
                print(f"检查schema失败: {e}")
            
            # 检查表
            try:
                with sync_engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'th'
                    """))
                    tables = [row[0] for row in result]
                    print(f"找到表: {tables}")
            except Exception as e:
                print(f"检查表失败: {e}")
            
            # 检查所有表（包括public schema）
            try:
                with sync_engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.tables 
                        WHERE table_schema IN ('th', 'public')
                        ORDER BY table_schema, table_name
                    """))
                    all_tables = [(row[0], row[1]) for row in result]
                    print(f"所有表: {all_tables}")
            except Exception as e:
                print(f"检查所有表失败: {e}")
            
            # 验证th.projects表是否存在
            try:
                with sync_engine.connect() as conn:
                    result = conn.execute(text("SELECT COUNT(*) FROM th.projects"))
                    count = result.scalar()
                    print(f"th.projects表存在，当前记录数: {count}")
            except Exception as e:
                print(f"th.projects表不存在或无法访问: {e}")
                    
        except Exception as e:
            print(f"迁移执行失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            sync_engine.dispose()
            
    finally:
        # 清理：删除临时数据库
        try:
            with maintenance_engine.connect() as conn:
                # 强制断开所有连接
                conn.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{temp_db_name}'"))
                conn.execute(text(f"DROP DATABASE {temp_db_name}"))
                print(f"成功删除临时数据库: {temp_db_name}")
        except Exception as e:
            print(f"删除临时数据库失败: {e}")
        finally:
            maintenance_engine.dispose()
    
    print("=== 测试完成 ===")


if __name__ == "__main__":
    asyncio.run(test_postgresql_migration())