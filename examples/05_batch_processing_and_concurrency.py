# examples/05_batch_processing_and_concurrency.py
"""
Trans-Hub v3.0 批量处理与并发示例 (重构版)
"""
import asyncio
import time
from examples._shared import example_runner, log
from trans_hub.core import TranslationResult

NUM_TASKS = 100
TARGET_LANGS = ["de", "fr", "es"]


async def process_concurrently_and_get_results(
    coordinator, langs: list[str]
) -> list[list[TranslationResult]]:
    """并发处理并返回所有结果。"""
    async def consume_and_return(lang: str) -> list[TranslationResult]:
        results = [res async for res in coordinator.process_pending_translations(lang)]
        log.info(f"Worker 为语言 '{lang}' 处理了 {len(results)} 个任务。")
        return results

    tasks = [asyncio.create_task(consume_and_return(lang)) for lang in langs]
    return await asyncio.gather(*tasks)


async def main() -> None:
    """执行批量处理与并发示例。"""
    async with example_runner("th_example_05.db") as coordinator:
        log.info(f"🚀 步骤 1: 正在快速提交 {NUM_TASKS} 个翻译请求...")
        start_time = time.monotonic()
        request_tasks = [
            coordinator.request(
                business_id=f"item.{i}",
                source_payload={"text": f"This is item number {i}"},
                target_langs=TARGET_LANGS,
            )
            for i in range(NUM_TASKS)
        ]
        await asyncio.gather(*request_tasks)
        duration = time.monotonic() - start_time
        log.info(f"✅ {NUM_TASKS * len(TARGET_LANGS)} 个任务条目提交完毕", duration=f"{duration:.2f}s")

        log.info(f"👷 步骤 2: 启动 {len(TARGET_LANGS)} 个并发 Worker...")
        start_time = time.monotonic()
        results_per_lang = await process_concurrently_and_get_results(coordinator, TARGET_LANGS)
        duration = time.monotonic() - start_time

        log.info("🔍 步骤 3: 验证处理结果...")
        total_processed = sum(len(results) for results in results_per_lang)
        log.info(f"🎉 所有 Worker 处理完毕", total_processed=total_processed, duration=f"{duration:.2f}s")
        assert total_processed == NUM_TASKS * len(TARGET_LANGS)
        log.info("✅ 验证通过！所有任务均已成功处理。")

if __name__ == "__main__":
    asyncio.run(main())