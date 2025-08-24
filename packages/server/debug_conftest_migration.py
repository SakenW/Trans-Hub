#!/usr/bin/env python3
# debug_conftest_migration.py
"""
调试conftest.py中migrated_db fixture的迁移问题
"""

import asyncio
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

# 添加src到路径
import sys
SRC_DIR = Path(__file__).parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trans_hub.bootstrap.init import load_config_with_validation
from trans_hub.management.config_utils import get_real_db_url
from trans_hub.infrastructure.db._schema import Base
from tests.helpers.tools.db_manager import managed_temp_database

async def debug_conftest_migration():
    """模拟conftest.py中的迁移过程"""
    
    # 加载配置
    config = load_config_with_validation("test")
    print(f"[DEBUG] 配置加载完成: {config.database.url}")
    
    # 获取维护库URL
    raw_maint_dsn = config.maintenance_database_url
    real_maint_dsn = get_real_db_url(raw_maint_dsn)
    maint_url = make_url(real_maint_dsn)
    
    print(f"[DEBUG] 维护库URL: {maint_url}")
    
    async with managed_temp_database(maint_url) as temp_db_url:
        print(f"[DEBUG] 临时数据库URL: {temp_db_url}")
        
        # 创建同步引擎
        sync_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+asyncpg", "+psycopg"
        )
        sync_engine = create_engine(sync_dsn)
        print(f"[DEBUG] 同步引擎URL: {sync_engine.url}")
        
        # 模拟conftest.py中的run_migrations函数
        alembic_ini_path = Path("alembic.ini")
        alembic_cfg = Config(str(alembic_ini_path))
        db_schema = alembic_cfg.get_main_option("db_schema", "public")
        
        print(f"[DEBUG] Alembic配置: db_schema={db_schema}")
        
        # 设置Alembic配置（模拟conftest.py中的设置）
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("db_schema", db_schema or "public")
        
        # 创建schema
        if db_schema and db_schema != "public":
            print(f"[DEBUG] 创建schema: {db_schema}")
            with sync_engine.connect() as connection:
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {db_schema}"))
                connection.commit()
                print(f"[DEBUG] Schema {db_schema} 创建完成")
        
        # 注入元数据和连接（模拟conftest.py）
        metadata = Base.metadata
        alembic_cfg.attributes["target_metadata"] = metadata
        
        print(f"[DEBUG] 元数据表数量: {len(metadata.tables)}")
        for table_name in list(metadata.tables.keys())[:5]:  # 只显示前5个
            print(f"[DEBUG] 表: {table_name}")
        
        # 执行迁移（模拟conftest.py中的方式）
        print("[DEBUG] 开始执行迁移...")
        try:
            with sync_engine.begin() as connection:
                # 注入连接
                alembic_cfg.attributes["connection"] = connection
                print(f"[DEBUG] 注入连接: {connection}")
                
                # 执行迁移
                command.upgrade(alembic_cfg, "head")
                print("[DEBUG] 迁移执行完成")
            
            print("[DEBUG] 迁移事务已提交")
            
            # 验证迁移结果
            print("[DEBUG] 验证迁移结果...")
            with sync_engine.connect() as conn:
                # 检查schema
                result = conn.execute(text(
                    "SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"
                ), {"schema": db_schema})
                schemas = result.fetchall()
                print(f"[DEBUG] Schema {db_schema} 存在: {len(schemas) > 0}")
                
                # 检查alembic_version表
                result = conn.execute(text(
                    f"SELECT version_num FROM {db_schema}.alembic_version"
                ))
                versions = result.fetchall()
                print(f"[DEBUG] Alembic版本: {versions}")
                
                # 检查projects表
                try:
                    result = conn.execute(text(
                        f"SELECT COUNT(*) FROM {db_schema}.projects"
                    ))
                    count = result.scalar()
                    print(f"[DEBUG] Projects表存在，行数: {count}")
                except Exception as e:
                    print(f"[DEBUG] Projects表不存在或查询失败: {e}")
                
                # 列出所有表
                result = conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"
                ), {"schema": db_schema})
                tables = [row[0] for row in result.fetchall()]
                print(f"[DEBUG] Schema {db_schema} 中的表: {tables}")
                
        except Exception as e:
            print(f"[DEBUG] 迁移执行失败: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(debug_conftest_migration())