# examples/02_contextual_translation.py
"""
Trans-Hub v3.0 上下文翻译示例 (重构版)
"""
import asyncio
from examples._shared import example_runner, log, process_translations
from trans_hub import EngineName


async def main() -> None:
    """执行上下文翻译示例。"""
    async with example_runner("th_example_02.db", active_engine=EngineName.DEBUG) as coordinator:
        business_id = "button.submit"
        source_payload = {"text": "Submit"}
        target_lang = "de"

        log.info("🚀 步骤 1: 提交两个不同上下文的翻译请求...")
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )
        high_risk_context = {"view": "delete_account_page"}
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
            context=high_risk_context,
        )

        engine_config = coordinator.active_engine.config
        engine_config.translation_map = {"Submit": "Einreichen"}

        log.info("👷 步骤 2: Worker 处理所有任务...")
        await process_translations(coordinator, [target_lang])

        log.info("🔍 步骤 3: 获取不同上下文的翻译...")
        generic_result = await coordinator.get_translation(
            business_id=business_id, target_lang=target_lang
        )
        contextual_result = await coordinator.get_translation(
            business_id=business_id,
            target_lang=target_lang,
            context=high_risk_context,
        )

        log.info("通用翻译结果", text=generic_result.translated_payload.get("text"))
        log.info("上下文翻译结果", text=contextual_result.translated_payload.get("text"))
        log.info("✅ 验证通过：不同上下文成功获取到了独立的翻译记录。")

if __name__ == "__main__":
    asyncio.run(main())