# tools/diag/simple_asyncpg_test.py
"""一个简化的脚本，用于测试 asyncpg.connect 调用。"""

import asyncio
import traceback

import asyncpg
from dotenv import load_dotenv
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestDatabaseConfig(BaseSettings):
    """用于测试 .env 文件中的数据库配置加载是否正常。"""

    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")
    database_url: PostgresDsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/trans_hub_test"  # 默认测试数据库URL


async def test_asyncpg_connection() -> None:
    """测试 asyncpg.connect 调用。"""
    print("--- asyncpg.connect 测试开始 ---")

    print("\n正在主动加载 .env 文件...")
    load_dotenv(verbose=True)

    print("\n正在创建 TestDatabaseConfig 实例...")
    config = TestDatabaseConfig()
    print("✅ 成功创建 TestDatabaseConfig 实例")

    # 转换 URL 格式以适配 asyncpg
    db_url = str(config.database_url).replace("postgresql+asyncpg://", "postgresql://")
    print(f"\n转换后的数据库 URL: {db_url}")

    print("\n正在尝试连接数据库...")
    try:
        # 使用 timeout 参数以避免无限期挂起
        connection = await asyncpg.connect(db_url, timeout=10.0)
        print("✅ 成功建立数据库连接")

        print("\n正在执行简单查询...")
        result = await connection.fetchval("SELECT 1")
        print(f"✅ 成功执行查询，结果: {result}")

        print("\n正在关闭数据库连接...")
        await connection.close()
        print("✅ 成功关闭数据库连接")

    except asyncio.TimeoutError:
        print("❌ 数据库连接超时")
        traceback.print_exc()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        traceback.print_exc()

    print("--- 测试结束 ---")


if __name__ == "__main__":
    asyncio.run(test_asyncpg_connection())
