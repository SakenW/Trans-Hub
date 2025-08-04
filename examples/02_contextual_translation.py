# examples/02_contextual_translation.py
"""
Trans-Hub v3.0 上下文翻译示例

本示例展示了如何为同一个 `business_id` 提供针对不同上下文的翻译：
1. 为一个按钮的文本 (`button.submit`) 提交一个通用翻译。
2. 为同一个按钮，在“高风险操作”上下文中，提供一个更明确、更警示的翻译。

运行方式:
在项目根目录执行: `poetry run python examples/02_contextual_translation.py`
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import List

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, EngineName, TransHubConfig  # noqa: E402
from trans_hub.core import TranslationResult  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger("trans_hub")

# --- 准备测试环境 ---
DB_FILE = Path(__file__).parent / "th_example_02.db"


async def main() -> None:
    """执行上下文翻译示例。"""
    if DB_FILE.exists():
        DB_FILE.unlink()

    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE.resolve()}",
        source_lang="en",
        active_engine=EngineName.DEBUG,
    )
    apply_migrations(config.db_path)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.info("✅ 协调器初始化成功", db_path=str(DB_FILE))

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
        if generic_result and generic_result.translated_payload:
            trans_text = generic_result.translated_payload.get("text")
            log.info("通用翻译结果", result=f"'Submit' -> '{trans_text}'")
            assert trans_text == "Einreichen"

        contextual_result = await coordinator.get_translation(
            business_id=business_id,
            target_lang=target_lang,
            context=high_risk_context,
        )
        if contextual_result and contextual_result.translated_payload:
            trans_text = contextual_result.translated_payload.get("text")
            log.info(
                "上下文翻译结果",
                context=high_risk_context,
                result=f"'Submit' -> '{trans_text}'",
            )
            assert trans_text == "Einreichen"

        log.info("✅ 验证通过：不同上下文成功获取到了独立的翻译记录。")

    finally:
        await coordinator.close()
        log.info("🚪 协调器已关闭")
        if DB_FILE.exists():
            DB_FILE.unlink()


async def process_translations(coordinator: Coordinator, langs: List[str]) -> None:
    """模拟 Worker 处理所有待办任务。"""
    tasks = [asyncio.create_task(consume_all(coordinator, lang)) for lang in langs]
    await asyncio.gather(*tasks)


async def consume_all(coordinator: Coordinator, lang: str) -> None:
    """消费指定语言的所有待办任务。"""
    results: List[TranslationResult] = [
        res async for res in coordinator.process_pending_translations(lang)
    ]
    log.info(f"Worker 为语言 '{lang}' 处理了 {len(results)} 个任务。")


if __name__ == "__main__":
    asyncio.run(main())