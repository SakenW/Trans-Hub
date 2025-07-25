# tests/diag/check_env.py (Mypy 最终修复版)
"""
一个独立的、最小化的脚本，用于验证 pydantic-settings
是否能从 .env 文件中成功加载 Trans-Hub 的配置。

运行方式:
 poetry run python tests/diag/check_env.py
"""

import traceback
from typing import Optional

from dotenv import load_dotenv
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

print("--- .env 加载测试开始 ---")

print("正在主动加载 .env 文件...")
dotenv_path = load_dotenv(verbose=True)

if dotenv_path:
    print(f"✅ python-dotenv 成功加载了 .env 文件: {dotenv_path}")
    try:
        with open(dotenv_path, encoding="utf-8") as f:
            print("\n.env 文件内容预览:")
            print("-" * 20)
            print(f.read().strip())
            print("-" * 20)
    except Exception as e:
        print(f"读取 .env 文件时出错: {e}")
else:
    print("⚠️ 警告: python-dotenv 未找到 .env 文件。配置将完全依赖于环境变量。")


class TestOpenAIConfig(BaseSettings):
    """用于测试 .env 文件中的 OpenAI 配置加载是否正常。"""

    model_config = SettingsConfigDict(env_prefix="TH_", env_file=".env", extra="ignore")
    openai_endpoint: Optional[HttpUrl] = None
    openai_api_key: Optional[SecretStr] = None
    openai_model: str = "default-model"


print("\n正在创建 TestOpenAIConfig 实例，尝试从环境加载配置...")
try:
    config = TestOpenAIConfig()

    print("\n--- 配置加载结果 ---")
    print(f"  config.openai_endpoint: {repr(config.openai_endpoint)}")
    print(f"  config.openai_api_key:  {repr(config.openai_api_key)}")
    print(f"  config.openai_model:    {repr(config.openai_model)}")

    print("\n--- 结果分析 ---")
    if config.openai_api_key:
        print("✅ 成功！openai_api_key 已从 .env 文件或环境变量中成功加载。")
    else:
        print("❌ 失败！openai_api_key 未能加载。请检查 .env 文件或环境变量。")

    if config.openai_endpoint:
        print("✅ 成功！openai_endpoint 已从 .env 文件或环境变量中成功加载。")
    else:
        print("❌ 失败！openai_endpoint 未能加载。请检查 .env 文件或环境变量。")

except Exception as e:
    # --- 核心修正：使用 traceback 打印完整的异常信息 ---
    print(f"\n在创建配置实例时发生严重错误: {e}")
    traceback.print_exc()

print("\n--- 测试结束 ---")
