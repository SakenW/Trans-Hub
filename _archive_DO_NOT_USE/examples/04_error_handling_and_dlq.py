# examples/04_error_handling_and_dlq.py
"""
Trans-Hub v3.0 错误处理与死信队列(DLQ)示例 (重构版)
"""
import asyncio
import aiosqlite
from examples._shared import example_runner, log, process_translations, current_dir
from trans_hub import EngineName
from trans_hub.config import RetryPolicyConfig

FAILING_TEXT = "This will always fail"


async def main() -> None:
    """执行错误处理与DLQ示例。"""
    db_file_path = current_dir / "th_example_04.db"
    
    # 定义此示例特有的配置
    config_overrides = {
        "active_engine": EngineName.DEBUG,
        "retry_policy": RetryPolicyConfig(max_attempts=1, initial_backoff=0.1),
        "engine_configs": {
            "debug": {
                "fail_on_text": FAILING_TEXT,
                "fail_is_retryable": True,
            }
        },
    }

    async with example_runner("th_example_04.db", **config_overrides) as coordinator:
        business_id = "task.that.fails"
        source_payload = {"text": FAILING_TEXT}
        target_lang = "de"

        log.info("🚀 步骤 1: 提交一个注定会失败的任务...")
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )

        log.info("👷 步骤 2: Worker 开始处理，预期会看到重试和最终失败日志...")
        await process_translations(coordinator, [target_lang])

        log.info("🔍 步骤 3: 自动验证任务是否已进入死信队列...")
        async with aiosqlite.connect(db_file_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM th_dead_letter_queue")
            row = await cursor.fetchone()
            assert row and row[0] == 1
        log.info("🎉 验证通过！任务已成功进入死信队列。")


if __name__ == "__main__":
    asyncio.run(main())