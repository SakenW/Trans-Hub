"""check_env.py

一个独立的、最小化的脚本，专门用于测试 pydantic-settings
是否能从 .env 文件中成功加载配置。
"""

import os
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

print("--- 开始 .env 加载测试 ---")
print(f"当前工作目录 (CWD): {os.getcwd()}")
print(f"期望的 .env 文件路径: {os.path.abspath('.env')}")

# 检查 .env 文件是否存在且可读
if os.path.isfile(".env"):
    print(".env 文件存在于当前目录。")
    try:
        with open(".env", encoding="utf-8") as f:
            print("\n.env 文件内容预览:")
            print("-" * 20)
            print(f.read().strip())
            print("-" * 20)
    except Exception as e:
        print(f"读取 .env 文件时出错: {e}")
else:
    print(".env 文件不存在于当前目录！")


# 定义一个与我们项目中 OpenAIEngineConfig 完全相同的配置模型
class TestConfig(BaseSettings):
    """用于测试 .env 文件中的 OpenAI 配置加载是否正常。"""

    model_config = SettingsConfigDict(
        env_prefix="TH_OPENAI_", env_file=".env", extra="ignore"
    )

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "default-model"


# --- 执行测试 ---
print("\n正在创建 TestConfig 实例，尝试加载配置...")
try:
    config = TestConfig()

    print("\n--- 配置加载结果 ---")
    # 使用 repr() 来清晰地显示值的类型 (e.g., 'some-string' vs None)
    print(f"  config.base_url: {repr(config.base_url)}")
    print(f"  config.api_key: {repr(config.api_key)}")
    print(f"  config.model: {repr(config.model)}")

    print("\n--- 结果分析 ---")
    if config.base_url:
        print("✅ 成功！base_url 已从 .env 文件中成功加载。")
    else:
        print("❌ 失败！base_url 未能加载。请检查 .env 文件内容和格式。")

    # 额外检查：环境变量是否被 `python-dotenv` 加载（如果它工作的话）
    print("\n检查 os.environ 是否包含已加载的变量...")
    env_var_value = os.getenv("TH_OPENAI_API_BASE_URL")
    if env_var_value:
        print(f"✅ os.getenv('TH_OPENAI_API_BASE_URL') 的值为: '{env_var_value}'")
    else:
        print("❌ os.getenv('TH_OPENAI_API_BASE_URL') 的值为 None。")


except Exception as e:
    print(f"\n在创建配置实例时发生严重错误: {e}")

print("\n--- 测试结束 ---")
