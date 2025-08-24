#!/usr/bin/env python3
# debug_offline_migration.py

import asyncio
import tempfile
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.trans_hub.bootstrap.init import load_config_with_validation
from src.trans_hub.management.config_utils import get_real_db_url

async def debug_offline_migration():
    """调试离线迁移模式，生成SQL并检查内容"""
    config = load_config_with_validation("test")
    
    # 创建临时数据库
    temp_db_name = f"th_debug_{hash(str(Path.cwd())) % 10000:04d}"
    maint_engine = create_async_engine(config.maintenance_database_url, isolation_level="AUTOCOMMIT")
    
    async with maint_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {temp_db_name}"))
        await conn.execute(text(f"CREATE DATABASE {temp_db_name}"))
    
    await maint_engine.dispose()
    
    # 构建临时数据库URL
    temp_url = config.database.url.replace("/transhub_test", f"/{temp_db_name}")
    print(f"[DEBUG] 临时数据库URL: {temp_url}")
    
    # 配置Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", get_real_db_url(temp_url))
    
    # 生成离线SQL
    sql_file = tempfile.mktemp(suffix='.sql')
    print(f"[DEBUG] 生成SQL文件: {sql_file}")
    
    # 使用离线模式生成SQL
    import sys
    from io import StringIO
    
    # 重定向stdout来捕获SQL输出
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    try:
        command.upgrade(alembic_cfg, "head", sql=True)
        sql_content = sys.stdout.getvalue()
    finally:
        sys.stdout = old_stdout
    
    # 写入SQL文件
    with open(sql_file, 'w') as f:
        f.write(sql_content)
    
    # 分析生成的SQL（已经在sql_content变量中）
    
    print("\n[DEBUG] 生成的SQL内容:")
    print("=" * 50)
    print(sql_content)
    print("=" * 50)
    
    # 分析SQL内容
    lines = sql_content.split('\n')
    create_table_lines = [line for line in lines if 'CREATE TABLE' in line.upper()]
    create_schema_lines = [line for line in lines if 'CREATE SCHEMA' in line.upper()]
    create_function_lines = [line for line in lines if 'CREATE FUNCTION' in line.upper() or 'CREATE OR REPLACE FUNCTION' in line.upper()]
    
    print(f"\n[DEBUG] SQL分析结果:")
    print(f"- CREATE SCHEMA语句数量: {len(create_schema_lines)}")
    print(f"- CREATE TABLE语句数量: {len(create_table_lines)}")
    print(f"- CREATE FUNCTION语句数量: {len(create_function_lines)}")
    
    if create_schema_lines:
        print(f"\n[DEBUG] Schema创建语句:")
        for line in create_schema_lines:
            print(f"  {line.strip()}")
    
    if create_table_lines:
        print(f"\n[DEBUG] 表创建语句:")
        for line in create_table_lines:
            print(f"  {line.strip()}")
    
    if create_function_lines:
        print(f"\n[DEBUG] 函数创建语句:")
        for line in create_function_lines[:3]:  # 只显示前3个
            print(f"  {line.strip()}")
    
    # 清理临时文件
    Path(sql_file).unlink()
    
    # 清理临时数据库
    maint_engine2 = create_async_engine(config.maintenance_database_url, isolation_level="AUTOCOMMIT")
    async with maint_engine2.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {temp_db_name}"))
    
    await maint_engine2.dispose()
    print(f"\n[DEBUG] 临时数据库 {temp_db_name} 已清理")

if __name__ == "__main__":
    asyncio.run(debug_offline_migration())