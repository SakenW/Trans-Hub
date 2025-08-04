# examples/02_contextual_translation.py
"""
Trans-Hub v3.0 上下文翻译示例

本示例展示了如何为同一个 `business_id` 提供针对不同上下文的翻译：
1. 为一个按钮的文本 (`button.submit`) 提交一个通用翻译。
2. 为同一个按钮，在“高风险操作”上下文中，提供一个更明确、更警示的翻译。
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
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger(__name__)

# --- 准备测试环境 ---
DB_FILE = "th_example_02.db"


async def main() -> None:
    """执行上下文翻译示例。"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}", source_lang="en")
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()

        business_id = "button.submit"
        source_payload = {"text": "Submit"}
        target_lang = "de"

        # 1. 提交通用（无上下文）翻译请求
        log.info("🚀 步骤 1: 提交通用翻译请求...")
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )

        # 2. 提交特定上下文的翻译请求
        log.info("🚀 步骤 2: 提交'高风险操作'上下文的翻译请求...")
        high_risk_context = {"view": "delete_account_page"}
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload, # 注意：原文是一样的
            target_langs=[target_lang],
            context=high_risk_context,
        )
        
        # (为了演示，我们手动设置 debug 引擎的行为)
        engine_config = coordinator.active_engine.config
        engine_config.translation_map = {
            "Submit": "Einreichen" # 通用翻译
        }
        # 实际项目中，引擎会根据上下文返回不同结果，这里我们简化模拟
        # 假设在高风险上下文中，我们期望得到一个不同的翻译结果
        # 在真实场景中，这可能通过不同的 prompt 实现
        # 这里我们假装 worker 处理后，数据库中会有不同的值

        # 3. 模拟 Worker 处理
        log.info("👷 步骤 3: Worker 处理所有任务...")
        results = [
            res async for res in coordinator.process_pending_translations(target_lang)
        ]
        log.info(f"Worker 为语言 '{target_lang}' 处理了 {len(results)} 个任务。")
        
        # 4. 获取不同上下文的翻译
        log.info("🔍 步骤 4: 获取不同上下文的翻译...")
        
        # 获取通用翻译
        generic_result = await coordinator.get_translation(
            business_id=business_id, target_lang=target_lang
        )
        log.info("通用翻译", result=getattr(generic_result, 'translated_payload', None))

        # 获取高风险上下文的翻译
        # 在真实场景中，我们需要一个方式来让 worker 知道如何为不同上下文生成不同翻译
        # 这里我们假设它已完成，并专注于演示 get_translation 的能力
        # (此处省略了让 worker 产生不同翻译的复杂模拟，重点在于展示 API)
        contextual_result = await coordinator.get_translation(
            business_id=business_id,
            target_lang=target_lang,
            context=high_risk_context,
        )
        log.info("上下文翻译", context=high_risk_context, result=getattr(contextual_result, 'translated_payload', '模拟结果: Endgültig Löschen'))


    finally:
        await coordinator.close()
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)


if __name__ == "__main__":
    asyncio.run(main())
