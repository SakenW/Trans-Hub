#!/usr/bin/env python3
# tools/check_translation_status.py

# 在所有导入之前加载 .env 文件
import os
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = Path(__file__).parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded .env file from {dotenv_path}")
else:
    print(f".env file not found at {dotenv_path}")

import asyncio  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import asyncpg  # noqa: E402

from trans_hub.config import TransHubConfig  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402


async def check_translation_status() -> None:
    # 使用与测试相同的数据库创建逻辑
    main_dsn = os.getenv("TH_DATABASE_URL")
    if not main_dsn:
        print("TH_DATABASE_URL environment variable is not set")
        return

    # 解析DSN
    parsed = urlparse(main_dsn)
    server_dsn = parsed._replace(path="").geturl()

    # 连接到服务器并列出所有测试数据库
    try:
        conn = await asyncpg.connect(dsn=server_dsn)
        rows = await conn.fetch(
            "SELECT datname FROM pg_database WHERE datname LIKE 'test_db_%' ORDER BY datname;"
        )
        test_databases = [row["datname"] for row in rows]
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
        # 查找测试用例创建的翻译任务
        business_id = "test.pg.force"
        target_lang = "de"

        # 使用PostgreSQL特定的方法获取连接
        # 由于这是工具脚本，我们可以直接访问PostgreSQL实现的内部方法
        if hasattr(handler, "_transaction"):
            async with handler._transaction() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        t.id,
                        t.status,
                        t.translation_payload_json
                    FROM th_translations t
                    JOIN th_content c
                        ON t.content_id = c.id
                    WHERE c.business_id = $1
                      AND t.lang_code = $2;
                    """,
                    business_id,
                    target_lang,
                )
        else:
            # 对于其他实现，使用通用方法
            # 这里简化处理，直接返回
            row = None

        if row:
            print(f"Translation ID: {row['id']}")
            print(f"Status: {row['status']}")
            print(f"Translation Payload: {row['translation_payload_json']}")
        else:
            print("No translation found for the test case")
    finally:
        await handler.close()


if __name__ == "__main__":
    asyncio.run(check_translation_status())
