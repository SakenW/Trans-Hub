# examples/01_core_workflow.py
"""
Trans-Hub v3.0 核心工作流示例

本示例展示了最基础的端到端流程：
1. 使用稳定的 `business_id` 和结构化的 `source_payload` 提交一个翻译请求。
2. 启动一个 worker 来处理待办任务。
3. 获取已完成的翻译结果。

运行方式:
在项目根目录执行: `poetry run python examples/01_core_workflow.py`
"""
import asyncio
import os
import sys
import logging
from pathlib import Path
from typing import List

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, TransHubConfig  # noqa: E402
from trans_hub.core import TranslationResult, TranslationStatus  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger("trans_hub")

# --- 准备测试环境 ---
DB_FILE = Path(__file__).parent / "th_example_01.db"


async def main() -> None:
    """执行核心工作流示例。"""
    if DB_FILE.exists():
        DB_FILE.unlink()

    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE.resolve()}", source_lang="en")
    apply_migrations(config.db_path)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.info("✅ 协调器初始化成功", db_path=str(DB_FILE))

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
            if result and result.status == TranslationStatus.TRANSLATED and result.translated_payload:
                original_text = result.original_payload.get("text", "[N/A]")
                translated_text = result.translated_payload.get("text", "[N/A]")
                log.info(
                    "🎉 成功获取翻译",
                    lang=lang,
                    result=f"'{original_text}' -> '{translated_text}'",
                )
            else:
                log.error("获取翻译失败", lang=lang, result=result)

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
    