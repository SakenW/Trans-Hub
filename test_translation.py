#!/usr/bin/env python3
# test_translation.py
"""
一个简单的测试脚本，直接调用Trans-Hub的API进行翻译。
用于测试程序是否能够正常结束。
"""

import asyncio
import sys
from pathlib import Path

# 设置项目路径
sys.path.insert(0, str(Path(__file__).parent))

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import create_persistence_handler


async def main() -> int:
    """主函数，用于测试翻译请求。"""
    setup_logging(log_level="INFO", log_format="console")

    config = TransHubConfig()
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        # 初始化协调器
        await coordinator.initialize()
        print("协调器初始化完成")

        # 提交翻译请求
        await coordinator.request(
            text_content="some text",
            target_langs=["zh-CN"],
            source_lang=None,
            business_id=None,
            force_retranslate=False,
        )
        print("✅ 翻译请求已成功提交！")

    except Exception as e:
        print(f"发生错误: {e}")
        return 1
    finally:
        # 关闭协调器
        await coordinator.close()
        print("协调器已关闭")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
