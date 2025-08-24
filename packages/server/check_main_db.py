#!/usr/bin/env python3
# check_main_db.py

from trans_hub.bootstrap.init import create_app_config
from sqlalchemy import create_engine, text

def main():
    config = create_app_config('test')
    sync_url = str(config.database.url).replace('+asyncpg', '+psycopg')
    engine = create_engine(sync_url)
    
    with engine.begin() as conn:
        # 检查alembic_version表
        try:
            result = conn.execute(text('SELECT version_num FROM th.alembic_version'))
            version = result.scalar()
            print(f'当前迁移版本: {version}')
            
            # 检查alembic_version表的所有内容
            result = conn.execute(text('SELECT * FROM th.alembic_version'))
            all_versions = result.fetchall()
            print(f'alembic_version表所有内容: {all_versions}')
            
            # 检查表结构
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'th' AND table_name = 'alembic_version'
            """))
            columns = result.fetchall()
            print(f'alembic_version表结构: {columns}')
        except Exception as e:
            print(f'查询alembic_version失败: {e}')
        
        # 检查表是否存在
        try:
            result = conn.execute(text("""
                SELECT schemaname, tablename 
                FROM pg_tables 
                WHERE schemaname = 'th'
                ORDER BY tablename
            """))
            tables = result.fetchall()
            print(f'th schema中的表: {[t[1] for t in tables]}')
        except Exception as e:
            print(f'查询表失败: {e}')
        
        # 检查函数是否存在
        try:
            result = conn.execute(text("""
                SELECT proname 
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = 'th' AND proname = 'is_bcp47'
            """))
            functions = result.fetchall()
            print(f'is_bcp47函数存在: {len(functions) > 0}')
        except Exception as e:
            print(f'查询函数失败: {e}')

if __name__ == '__main__':
    main()