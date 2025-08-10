# tools/diag/test_db_connection.py
"""
一个独立的、最小化的脚本，用于验证 Trans-Hub 的数据库连接配置是否正确。

运行方式:
 poetry run python tools/diag/test_db_connection.py
"""

import asyncio
import traceback
from typing import Any

import asyncpg
from dotenv import load_dotenv
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

print("--- 数据库连接测试开始 ---")

print("正在主动加载 .env 文件...")
dotenv_path = load_dotenv(verbose=True)

if dotenv_path:
    print(f"✅ python-dotenv 成功加载了 .env 文件: {dotenv_path}")
else:
    print("⚠️ 警告: python-dotenv 未找到 .env 文件。配置将完全依赖于环境变量。")


class TestDatabaseConfig(BaseSettings):
    """用于测试 .env 文件中的数据库配置加载是否正常。"""

    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")
    database_url: PostgresDsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/trans_hub_test"  # 默认测试数据库URL


async def test_connection(config: TestDatabaseConfig) -> dict[str, Any]:
    """测试数据库连接。"""
    print(f"\n尝试连接到数据库: {config.database_url}")

    # 转换 URL 格式以适配 asyncpg
    db_url = str(config.database_url).replace("postgresql+asyncpg://", "postgresql://")
    print(f"\n转换后的数据库 URL: {db_url}")

    # 提取并打印连接参数以供调试
    from urllib.parse import urlparse

    parsed_url = urlparse(db_url)
    print("\n连接参数调试信息:")
    print(f"  主机: {parsed_url.hostname}")
    print(f"  端口: {parsed_url.port}")
    print(f"  数据库名: {parsed_url.path[1:] if parsed_url.path else ''}")
    print(f"  用户名: {parsed_url.username}")

    try:
        # 使用 timeout 参数以避免无限期挂起
        print("\n正在尝试连接数据库...")
        connection = await asyncpg.connect(db_url, timeout=10.0)
        print("✅ 成功建立数据库连接")

        print("\n正在执行简单查询...")
        result = await connection.fetchval("SELECT 1")
        print(f"✅ 成功执行查询，结果: {result}")

        print("\n正在关闭数据库连接...")
        await connection.close()
        print("✅ 成功关闭数据库连接")

        return {"success": True, "result": result}
    except asyncio.TimeoutError:
        print("❌ 数据库连接超时")
        traceback.print_exc()
        return {"success": False, "error": "连接超时"}
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def main() -> None:
    """主函数。"""
    print("\n正在创建 TestDatabaseConfig 实例，尝试从环境加载配置...")
    try:
        print("创建配置实例前...")
        config = TestDatabaseConfig()
        print("创建配置实例后...")
        print("\n--- 配置加载结果 ---")
        print(f"  config.database_url: {repr(config.database_url)}")

        print("\n--- 开始测试数据库连接 ---")
        result = await test_connection(config)

        print("\n--- 测试结果 ---")
        if result["success"]:
            print("✅ 数据库连接测试成功！")
        else:
            print("❌ 数据库连接测试失败！")
            print(f"错误详情: {result['error']}")

    except Exception as e:
        # --- 核心修正：使用 traceback 打印完整的异常信息 ---
        print(f"\n在创建配置实例时发生严重错误: {e}")
        traceback.print_exc()

    print("\n--- 测试结束 ---")


if __name__ == "__main__":
    asyncio.run(main())
