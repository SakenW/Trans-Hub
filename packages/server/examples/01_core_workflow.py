# examples/01_core_workflow.py
"""
Trans-Hub v3.0 核心工作流示例 (重构版)

本示例展示了最基础的端到端流程：
1. 使用稳定的 `business_id` 和结构化的 `source_payload` 提交一个翻译请求。
2. 启动一个 worker 来处理待办任务。
3. 获取已完成的翻译结果。

运行方式:
在项目根目录执行: `poetry run python examples/01_core_workflow.py`
"""
import asyncio
from examples._shared import example_runner, log, process_translations
from trans_hub.core import TranslationStatus


async def main() -> None:
    """执行核心工作流示例。"""
    async with example_runner("th_example_01.db") as coordinator:
        business_id = "onboarding.welcome_title"
        source_payload = {"text": "Welcome to Our App!", "max_length": 50}
        target_langs = ["de", "zh-CN"]

        log.info("🚀 步骤 1: 提交翻译请求...", business_id=business_id)
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=target_langs,
        )

        log.info("👷 步骤 2: 启动 Worker 处理任务...", langs=target_langs)
        await process_translations(coordinator, target_langs)

        log.info("🔍 步骤 3: 获取并验证翻译结果...")
        for lang in target_langs:
            result = await coordinator.get_translation(
                business_id=business_id, target_lang=lang
            )
            if result and result.status == TranslationStatus.TRANSLATED:
                original_text = result.original_payload.get("text", "[N/A]")
                translated_text = result.translated_payload.get("text", "[N/A]")
                log.info(
                    "🎉 成功获取翻译",
                    lang=lang,
                    result=f"'{original_text}' -> '{translated_text}'",
                )
            else:
                log.error("获取翻译失败", lang=lang, result=result)

if __name__ == "__main__":
    asyncio.run(main())