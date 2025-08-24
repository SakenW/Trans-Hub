#!/usr/bin/env python3
"""
测试迁移执行的调试脚本
"""

import sys
from pathlib import Path

# 添加src目录到路径
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from trans_hub.bootstrap.init import load_config_with_validation
from trans_hub.infrastructure.db._schema import Base
from trans_hub.management.config_utils import get_real_db_url
from tests.helpers.tools.db_manager import managed_temp_database_sync
from sqlalchemy.engine import make_url


def test_migration_step_by_step():
    """逐步测试迁移过程"""
    print("=== 开始迁移调试 ===")
    
    # 加载配置
    config = load_config_with_validation(env_mode="test")
    raw_maint_dsn = config.maintenance_database_url
    if not raw_maint_dsn:
        print("错误：维护库 DSN 未配置")
        return
    
    real_maint_dsn = get_real_db_url(raw_maint_dsn)
    maint_url = make_url(real_maint_dsn)
    
    with managed_temp_database_sync(maint_url) as temp_db_url:
        sync_dsn = temp_db_url.render_as_string(hide_password=False)
        sync_engine = create_engine(sync_dsn)
        
        print(f"临时数据库: {sync_dsn}")
        
        # 检查初始状态
        with sync_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT schemaname, tablename 
                FROM pg_tables 
                WHERE schemaname IN ('th', 'public')
                ORDER BY schemaname, tablename
            """))
            tables = result.fetchall()
            print(f"初始表: {tables}")
        
        # 配置Alembic
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_dsn)
        alembic_cfg.set_main_option("db_schema", "th")
        alembic_cfg.attributes["target_metadata"] = Base.metadata
        
        print("\n=== 执行完整迁移到head ===")
        try:
            with sync_engine.begin() as connection:
                alembic_cfg.attributes["connection"] = connection
                command.upgrade(alembic_cfg, "head")
                print("迁移到head完成")
        except Exception as e:
            print(f"迁移执行失败: {e}")
            import traceback
            traceback.print_exc()
            
        # 检查迁移后的状态
        try:
            with sync_engine.begin() as connection:
                # 检查迁移后的状态
                result = connection.execute(text("""
                    SELECT schemaname, tablename 
                    FROM pg_tables 
                    WHERE schemaname IN ('th', 'public')
                    ORDER BY schemaname, tablename
                """))
                tables = result.fetchall()
                print(f"迁移后的表: {tables}")
                
                # 检查函数是否存在
                result = connection.execute(text("""
                    SELECT proname 
                    FROM pg_proc p 
                    JOIN pg_namespace n ON p.pronamespace = n.oid 
                    WHERE n.nspname = 'th' AND proname = 'is_bcp47'
                """))
                functions = result.fetchall()
                print(f"is_bcp47函数: {functions}")
                
                # 检查projects表是否存在
                result = connection.execute(text("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'th' AND table_name = 'projects'
                    )
                """))
                projects_exists = result.scalar()
                print(f"projects表存在: {projects_exists}")
                
                # 检查content表是否存在
                result = connection.execute(text("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'th' AND table_name = 'content'
                    )
                """))
                content_exists = result.scalar()
                print(f"content表存在: {content_exists}")
                
                # 检查当前迁移版本
                try:
                    result = connection.execute(text("""
                        SELECT version_num FROM th.alembic_version LIMIT 1
                    """))
                    current_version = result.scalar()
                    print(f"当前迁移版本: {current_version}")
                except Exception as e:
                    print(f"查询alembic_version失败: {e}")
                    
                # 检查alembic_version表的所有内容
                try:
                    result = connection.execute(text("""
                        SELECT * FROM th.alembic_version
                    """))
                    all_versions = result.fetchall()
                    print(f"alembic_version表内容: {all_versions}")
                except Exception as e:
                    print(f"查询alembic_version表内容失败: {e}")
                
        except Exception as e:
            print(f"迁移失败: {e}")
            import traceback
            traceback.print_exc()
            return
        
        print("\n=== 迁移调试完成 ===")
        sync_engine.dispose()


if __name__ == "__main__":
    test_migration_step_by_step()