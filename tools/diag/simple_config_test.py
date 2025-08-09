# tools/diag/simple_config_test.py
"""
一个简化的脚本，用于测试 TestDatabaseConfig 类的实例化。
"""

import os
import traceback
from dotenv import load_dotenv
from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestDatabaseConfig(BaseSettings):
    """用于测试 .env 文件中的数据库配置加载是否正常。"""

    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")
    database_url: PostgresDsn


def test_config_instantiation() -> None:
    """测试 TestDatabaseConfig 类的实例化。"""
    print("--- TestDatabaseConfig 实例化测试开始 ---")
    
    print("\n正在主动加载 .env 文件...")
    load_dotenv(verbose=True)
    
    print("\n环境变量 TH_DATABASE_URL:")
    db_url = os.environ.get("TH_DATABASE_URL")
    if db_url:
        print(f"  {db_url}")
    else:
        print("  未找到 TH_DATABASE_URL 环境变量")
    
    print("\n正在创建 TestDatabaseConfig 实例...")
    try:
        config = TestDatabaseConfig()
        print("✅ 成功创建 TestDatabaseConfig 实例")
        print(f"  config.database_url: {repr(config.database_url)}")
    except Exception as e:
        print(f"❌ 创建 TestDatabaseConfig 实例失败: {e}")
        traceback.print_exc()
    
    print("--- 测试结束 ---")


if __name__ == "__main__":
    test_config_instantiation()