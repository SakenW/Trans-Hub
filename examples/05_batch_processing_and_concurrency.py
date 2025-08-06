# examples/05_batch_processing_and_concurrency.py
"""
Trans-Hub v3.0 批量处理与并发示例

本示例展示了系统处理大量任务的能力：
1. 在一个循环中快速提交大量（例如100个）独立的翻译请求。
2. 启动多个并发的 Worker (AsyncIO Task) 来同时处理不同语言的任务。
3. 统计并验证所有任务是否都已成功处理。

运行方式:
在项目根目录执行: `poetry run python examples/05_batch_processing_and_concurrency.py`
"""

import asyncio
import sys
import time
from pathlib import Path

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, TransHubConfig  # noqa: E402
from trans_hub.core import TranslationResult  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="WARNING")
log = structlog.get_logger("trans_hub")

# --- 准备测试环境 ---
DB_FILE = Path(__file__).parent / "th_example_05.db"
NUM_TASKS = 100
TARGET_LANGS = ["de", "fr", "es"]


async def main() -> None:
    """执行批量处理与并发示例。"""
    if DB_FILE.exists():
        DB_FILE.unlink()

    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE.resolve()}", source_lang="en"
    )
    apply_migrations(config.db_path)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.warning("✅ 协调器初始化成功", db_path=str(DB_FILE))

        log.warning(f"🚀 步骤 1: 正在快速提交 {NUM_TASKS} 个翻译请求...")
        start_time = time.monotonic()
        request_tasks = []
        for i in range(NUM_TASKS):
            task = coordinator.request(
                business_id=f"item.{i}",
                source_payload={"text": f"This is item number {i}"},
                target_langs=TARGET_LANGS,
            )
            request_tasks.append(task)
        await asyncio.gather(*request_tasks)
        duration = time.monotonic() - start_time
        log.warning(
            f"✅ {NUM_TASKS * len(TARGET_LANGS)} 个任务条目提交完毕，耗时: {duration:.2f}s"
        )

        log.warning(f"👷 步骤 2: 启动 {len(TARGET_LANGS)} 个并发 Worker...")
        start_time = time.monotonic()
        results_per_lang = await process_translations_with_results(
            coordinator, TARGET_LANGS
        )
        duration = time.monotonic() - start_time

        log.warning("🔍 步骤 3: 验证处理结果...")
        total_processed = sum(len(results) for results in results_per_lang)
        log.warning(
            f"🎉 所有 Worker 处理完毕，共处理 {total_processed} 个任务，耗时: {duration:.2f}s"
        )
        assert total_processed == NUM_TASKS * len(TARGET_LANGS)
        log.warning("✅ 验证通过！所有任务均已成功处理。")

    finally:
        await coordinator.close()
        log.warning("🚪 协调器已关闭")
        if DB_FILE.exists():
            DB_FILE.unlink()


async def process_translations_with_results(
    coordinator: Coordinator, langs: list[str]
) -> list[list[TranslationResult]]:
    """模拟 Worker 处理所有待办任务并返回结果。"""
    tasks = [
        asyncio.create_task(consume_all_and_return(coordinator, lang)) for lang in langs
    ]
    return await asyncio.gather(*tasks)


async def consume_all_and_return(
    coordinator: Coordinator, lang: str
) -> list[TranslationResult]:
    """消费指定语言的所有待办任务并返回结果列表。"""
    results = [res async for res in coordinator.process_pending_translations(lang)]
    log.info(f"Worker 为语言 '{lang}' 处理了 {len(results)} 个任务。")
    return results


if __name__ == "__main__":
    asyncio.run(main())
