# tools/diag/simple_env_test.py
"""一个简化的脚本，用于测试 .env 文件加载。"""

import os

from dotenv import load_dotenv


def test_env_loading() -> None:
    """测试 .env 文件加载。"""
    print("--- .env 文件加载测试开始 ---")

    print("当前工作目录:", os.getcwd())
    print(".env 文件是否存在:", os.path.exists(".env"))

    if os.path.exists(".env"):
        print(".env 文件大小:", os.path.getsize(".env"))

    print("\n正在主动加载 .env 文件...")
    dotenv_path = load_dotenv(verbose=True)
    print("load_dotenv 返回值:", dotenv_path)

    print("\n环境变量 TH_DATABASE_URL:")
    db_url = os.environ.get("TH_DATABASE_URL")
    if db_url:
        print(f"  {db_url}")
    else:
        print("  未找到 TH_DATABASE_URL 环境变量")

    print("--- 测试结束 ---")


if __name__ == "__main__":
    test_env_loading()
