#!/usr/bin/env python3
# tools/check_translation_status.py

# 在所有导入之前加载 .env 文件
import os
from pathlib import Path
from dotenv import load_dotenv

dotenv_path = Path(__file__).parent.parent / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded .env file from {dotenv_path}")
else:
    print(f".env file not found at {dotenv_path}")

import asyncio
from urllib.parse import urlparse

import asyncpg

from trans_hub.config import TransHubConfig
from trans_hub.persistence import create_persistence_handler

async def check_translation_status() -> None:
    # 使用与测试相同的数据库创建逻辑
    main_dsn = os.getenv('TH_DATABASE_URL')
    if not main_dsn:
        print('TH_DATABASE_URL environment variable is not set')
        return
    
    # 解析DSN
    parsed = urlparse(main_dsn)
    server_dsn = parsed._replace(path="").geturl()
    
    # 连接到服务器并列出所有测试数据库
    try:
        conn = await asyncpg.connect(dsn=server_dsn)
        rows = await conn.fetch("SELECT datname FROM pg_database WHERE datname LIKE 'test_db_%' ORDER BY datname;")
        test_databases = [row['datname'] for row in rows]
        await conn.close()
        
        if not test_databases:
            print("No test databases found")
            return
        
        # 使用最新的测试数据库
        db_name = test_databases[-1]
        print(f"Using test database: {db_name}")
        test_db_dsn = parsed._replace(path=f"/{db_name}").geturl()
    except Exception as e:
        print(f"Failed to list test databases: {e}")
        return
    
    # 连接到测试数据库
    config = TransHubConfig(database_url=test_db_dsn)
    handler = create_persistence_handler(config)
    await handler.connect()
    
    try:
        # 修复：查询一个在测试中真实存在的 business_id，如 'test.pg.stale_item'
        business_id = "test.pg.stale_item"
        target_lang = "de"
        print(f"\nQuerying for business_id='{business_id}', target_lang='{target_lang}'")
        
        # 修复：使用更健壮的 find_translation 公共接口，而不是直接执行 SQL
        result = await handler.find_translation(
            business_id=business_id,
            target_lang=target_lang,
            context=None
        )
            
        if result:
            print(f"Translation ID: {result.translation_id}")
            print(f"Status: {result.status.value}")
            print(f"Original Payload: {result.original_payload}")
            print(f"Translation Payload: {result.translated_payload}")
            print(f"Error: {result.error}")
        else:
            print(f"No translation found for business_id='{business_id}' and lang='{target_lang}'")
    finally:
        await handler.close()

if __name__ == "__main__":
    asyncio.run(check_translation_status())