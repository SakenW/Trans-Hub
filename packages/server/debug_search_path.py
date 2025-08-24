#!/usr/bin/env python3
# debug_search_path.py

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from trans_hub.bootstrap.init import load_config_with_validation
from trans_hub.management.config_utils import get_real_db_url
from sqlalchemy.engine import make_url
from tests.helpers.tools.db_manager import managed_temp_database
from alembic.config import Config
from sqlalchemy import create_engine
from tests.conftest import run_migrations
from pathlib import Path

SERVER_PACKAGE_ROOT = Path(__file__).parent

async def debug_search_path():
    """调试异步引擎的search_path设置问题"""
    print("=== 调试异步引擎search_path设置 ===")
    
    # 加载配置
    config = load_config_with_validation("test")
    
    # 获取维护库URL
    raw_maint_dsn = config.maintenance_database_url
    real_maint_dsn = get_real_db_url(raw_maint_dsn)
    maint_url = make_url(real_maint_dsn)
    
    async with managed_temp_database(maint_url) as temp_db_url:
        print(f"临时数据库URL: {temp_db_url}")
        
        # 1. 创建同步引擎并执行迁移
        sync_dsn = temp_db_url.render_as_string(hide_password=False).replace(
            "+asyncpg", "+psycopg"
        )
        sync_engine = create_engine(sync_dsn)
        
        # 执行迁移
        alembic_ini_path = SERVER_PACKAGE_ROOT / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))
        db_schema = alembic_cfg.get_main_option("db_schema", "public")
        print(f"目标schema: {db_schema}")
        
        run_migrations(sync_engine, db_schema)
        sync_engine.dispose()
        
        # 2. 测试不同的异步引擎配置
        real_temp_dsn = get_real_db_url(temp_db_url.render_as_string(hide_password=False))
        
        # 方法1: 使用URL参数设置search_path（当前方法）
        async_dsn_1 = real_temp_dsn
        if db_schema and db_schema != "public":
            separator = "&" if "?" in async_dsn_1 else "?"
            async_dsn_1 += f"{separator}options=-csearch_path%3D{db_schema}%2Cpublic"
        
        print(f"\n方法1 - URL参数设置search_path:")
        print(f"URL: {async_dsn_1}")
        
        async_engine_1 = create_async_engine(async_dsn_1)
        async with async_engine_1.begin() as conn:
            # 检查当前search_path
            result = await conn.execute(text("SHOW search_path"))
            search_path = result.scalar()
            print(f"当前search_path: {search_path}")
            
            # 检查schema中的表
            result = await conn.execute(text("""
                SELECT schemaname, tablename
                FROM pg_tables
                WHERE schemaname = 'th'
                ORDER BY tablename
            """))
            tables = result.fetchall()
            print(f"th schema中的表: {[t[1] for t in tables]}")
            
            # 尝试查询projects表（不指定schema）
            try:
                result = await conn.execute(text("SELECT COUNT(*) FROM projects"))
                count = result.scalar()
                print(f"查询projects表成功（不指定schema）: {count}")
            except Exception as e:
                print(f"查询projects表失败（不指定schema）: {e}")
            
            # 尝试查询projects表（指定schema）
            try:
                result = await conn.execute(text("SELECT COUNT(*) FROM th.projects"))
                count = result.scalar()
                print(f"查询th.projects表成功: {count}")
            except Exception as e:
                print(f"查询th.projects表失败: {e}")
        
        await async_engine_1.dispose()
        
        # 方法2: 在连接时设置search_path
        print(f"\n方法2 - 连接时设置search_path:")
        async_engine_2 = create_async_engine(real_temp_dsn)
        async with async_engine_2.begin() as conn:
            # 手动设置search_path
            if db_schema and db_schema != "public":
                await conn.execute(text(f"SET search_path TO {db_schema}, public"))
            
            # 检查当前search_path
            result = await conn.execute(text("SHOW search_path"))
            search_path = result.scalar()
            print(f"当前search_path: {search_path}")
            
            # 尝试查询projects表（不指定schema）
            try:
                result = await conn.execute(text("SELECT COUNT(*) FROM projects"))
                count = result.scalar()
                print(f"查询projects表成功（不指定schema）: {count}")
            except Exception as e:
                print(f"查询projects表失败（不指定schema）: {e}")
            
            # 尝试查询projects表（指定schema）
            try:
                result = await conn.execute(text("SELECT COUNT(*) FROM th.projects"))
                count = result.scalar()
                print(f"查询th.projects表成功: {count}")
            except Exception as e:
                print(f"查询th.projects表失败: {e}")
        
        await async_engine_2.dispose()

if __name__ == "__main__":
    asyncio.run(debug_search_path())