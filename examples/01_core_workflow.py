# examples/01_core_workflow.py
"""
Trans-Hub v3.0 核心工作流示例

本示例展示了最基础的端到端流程：
1. 使用稳定的 `business_id` 和结构化的 `source_payload` 提交一个翻译请求。
2. 启动一个 worker 来处理待办任务。
3. 获取已完成的翻译结果。
"""
import asyncio
import os
import sys
from pathlib import Path

import structlog

# --- 路径设置，确保能找到 trans_hub 模块 ---
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
DB_FILE = "th_example_01.db"


async def main() -> None:
    """执行核心工作流示例。"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}", source_lang="en")
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.info("✅ 协调器初始化成功", db_path=DB_FILE)

        business_id = "onboarding.welcome_title"
        source_payload = {"text": "Welcome to Our App!", "max_length": 50}
        target_langs = ["de", "zh-CN"]

        # 1. 提交翻译请求
        log.info("🚀 步骤 1: 提交翻译请求...", business_id=business_id)
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=target_langs,
        )

        # 2. 启动 Worker 处理任务 (在一个单独的 task 中模拟)
        log.info("👷 步骤 2: 启动 Worker 处理任务...", langs=target_langs)
        worker_task = asyncio.create_task(process_translations(coordinator, target_langs))
        await worker_task

        # 3. 获取并验证翻译结果
        log.info("🔍 步骤 3: 获取并验证翻译结果...")
        for lang in target_langs:
            result = await coordinator.get_translation(
                business_id=business_id, target_lang=lang
            )
            if result and result.status == TranslationStatus.TRANSLATED:
                log.info(
                    "🎉 成功获取翻译",
                    lang=lang,
                    original=result.original_payload,
                    translated=result.translated_payload,
                )
            else:
                log.error("获取翻译失败", lang=lang, result=result)

    finally:
        await coordinator.close()
        log.info("🚪 协调器已关闭")
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)


async def process_translations(coordinator: Coordinator, langs: list[str]) -> None:
    """模拟 Worker 处理所有待办任务。"""
    tasks = [
        asyncio.create_task(consume_all(coordinator, lang)) for lang in langs
    ]
    await asyncio.gather(*tasks)


async def consume_all(coordinator: Coordinator, lang: str) -> None:
    """消费指定语言的所有待办任务。"""
    results: list[TranslationResult] = [
        res async for res in coordinator.process_pending_translations(lang)
    ]
    log.info(f"Worker 为语言 '{lang}' 处理了 {len(results)} 个任务。")


if __name__ == "__main__":
    asyncio.run(main())
