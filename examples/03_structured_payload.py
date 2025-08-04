# examples/03_structured_payload.py
"""
Trans-Hub v3.0 结构化载荷示例

本示例展示了如何处理一个不仅仅是简单文本的复杂 payload：
1. 定义一个包含文本、链接和元数据的结构化 payload。
2. 提交翻译请求。
3. 验证 Worker 处理后，只有 `text` 字段被翻译，而其他字段保持不变。
"""
import asyncio
import os
import sys
from pathlib import Path

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, TransHubConfig  # noqa: E402
from trans_hub.core import TranslationResult, TranslationStatus  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger(__name__)

# --- 准备测试环境 ---
DB_FILE = "th_example_03.db"


async def main() -> None:
    """执行结构化载荷示例。"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}", source_lang="en")
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()

        business_id = "component.call_to_action"
        source_payload = {
            "text": "Learn More",
            "link_url": "/docs/getting-started",
            "style": "primary_button",
            "track_id": "cta-learn-more"
        }
        target_lang = "fr"

        # 1. 提交包含结构化载荷的翻译请求
        log.info("🚀 步骤 1: 提交结构化载荷请求...", payload=source_payload)
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )

        # 2. 模拟 Worker 处理
        log.info("👷 步骤 2: Worker 处理任务...")
        results: list[TranslationResult] = [
            res async for res in coordinator.process_pending_translations(target_lang)
        ]
        log.info(f"Worker 为语言 '{target_lang}' 处理了 {len(results)} 个任务。")
        
        # 3. 获取结果并验证结构
        log.info("🔍 步骤 3: 获取结果并验证结构...")
        result = await coordinator.get_translation(business_id, target_lang)

        if result and result.status == TranslationStatus.TRANSLATED:
            log.info("🎉 成功获取翻译", translated=result.translated_payload)
            
            # 验证
            original = result.original_payload
            translated = result.translated_payload or {}
            
            assert translated.get("text") != original.get("text")
            assert translated.get("link_url") == original.get("link_url")
            assert translated.get("style") == original.get("style")
            
            log.info("✅ 验证通过: 只有 'text' 字段被翻译，其他元数据保留不变。")
        else:
            log.error("获取翻译失败", result=result)

    finally:
        await coordinator.close()
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)


if __name__ == "__main__":
    asyncio.run(main())
