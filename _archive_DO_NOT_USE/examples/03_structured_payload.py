# examples/03_structured_payload.py
"""
Trans-Hub v3.0 结构化载荷示例 (重构版)
"""
import asyncio
from examples._shared import example_runner, log, process_translations
from trans_hub.core import TranslationStatus


async def main() -> None:
    """执行结构化载荷示例。"""
    async with example_runner("th_example_03.db") as coordinator:
        business_id = "component.call_to_action"
        source_payload = {
            "text": "Learn More",
            "link_url": "/docs/getting-started",
            "style": "primary_button",
        }
        target_lang = "fr"

        log.info("🚀 步骤 1: 提交结构化载荷请求...", payload=source_payload)
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )

        log.info("👷 步骤 2: Worker 处理任务...")
        await process_translations(coordinator, [target_lang])

        log.info("🔍 步骤 3: 获取结果并验证结构...")
        result = await coordinator.get_translation(business_id, target_lang)

        if result and result.status == TranslationStatus.TRANSLATED:
            original = result.original_payload
            translated = result.translated_payload or {}
            log.info("🎉 成功获取翻译", translated_payload=translated)
            assert translated.get("text") != original.get("text")
            assert translated.get("link_url") == original.get("link_url")
            log.info("✅ 验证通过: 只有 'text' 字段被翻译，其他元数据保留不变。")
        else:
            log.error("获取翻译失败", result=result)

if __name__ == "__main__":
    asyncio.run(main())