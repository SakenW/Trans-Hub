# tools/diag/verify_api.py
"""
一个与 Trans-Hub 完全无关的独立脚本，
用于直接验证 OpenAI 兼容 API 的连通性。

安装依赖:
  pip install httpx python-dotenv

运行方式:
  python tools/diag/verify_api.py
"""

import os

import httpx
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

API_KEY = os.getenv("TH_OPENAI_API_KEY")
API_ENDPOINT = os.getenv("TH_OPENAI_ENDPOINT", "https://api.openai.com/v1")
API_MODEL = os.getenv("TH_OPENAI_MODEL", "gpt-3.5-turbo")

if not API_KEY or "sk-" not in API_KEY:
    print("❌ 错误: TH_OPENAI_API_KEY 未在 .env 文件中设置或格式不正确。")
    exit(1)

print("=" * 60)
print(" API 连通性直接验证")
print("=" * 60)
print(f"  - Endpoint: {API_ENDPOINT}")
print(f"  - Model:    {API_MODEL}")
print(f"  - API Key:  sk-....{API_KEY[-4:]}")  # 只显示最后4位
print("-" * 60)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

data = {
    "model": API_MODEL,
    "messages": [{"role": "user", "content": "Translate 'Hello' to French."}],
    "temperature": 0.1,
}

try:
    print("... 正在发送 API 请求 ...")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{API_ENDPOINT.strip('/')}/chat/completions",
            headers=headers,
            json=data,
        )

    print("\n✅ 请求完成！")
    print(f"  - HTTP 状态码: {response.status_code}")
    print("  - 响应体 (部分):")
    try:
        response_json = response.json()
        print(response_json)
        if response.is_success:
            print("\n" + "=" * 60)
            print("🎉 恭喜！API 连通性验证成功！")
            print("=" * 60)
            print("这意味着 Trans-Hub 中的问题可能是由其他细微配置差异引起的。")
        else:
            print("\n" + "=" * 60)
            print("❌ 失败！API 返回了错误状态码。")
            print("=" * 60)
            print("请检查 API Key、Endpoint、模型名称和您的账户权限。")

    except Exception:
        print(response.text[:500] + "...")


except httpx.RequestError as e:
    print("\n" + "=" * 60)
    print("❌ 严重错误: 网络请求失败！")
    print("=" * 60)
    print(f"错误类型: {type(e).__name__}")
    print(f"错误信息: {e}")
    print("请检查您的网络连接、DNS设置，以及 API Endpoint 地址是否正确。")
