# examples/04_error_handling_and_dlq.py
"""
Trans-Hub v3.0 错误处理与死信队列(DLQ)示例

本示例展示了系统如何处理持续失败的任务：
1. 配置一个必定会失败的 Debug 引擎和快速重试策略。
2. 提交一个会触发失败条件的任务。
3. 启动 Worker，观察任务的重试与最终失败。
4. 自动验证失败的任务是否已被正确地移入死信队列。

运行方式:
在项目根目录执行: `poetry run python examples/04_error_handling_and_dlq.py`
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import List

import aiosqlite
import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, EngineName, TransHubConfig  # noqa: E402
from trans_hub.config import RetryPolicyConfig  # noqa: E402
from trans_hub.core import TranslationResult  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
# v3.7 优化：在示例中，使用 debug 级别日志以观察详细的重试过程
# from trans_hub.logging_config import setup_logging
# setup_logging(log_level="DEBUG")
log = structlog.get_logger("trans_hub")

# --- 准备测试环境 ---
DB_FILE = Path(__file__).parent / "th_example_04.db"
FAILING_TEXT = "This will always fail"


async def main() -> None:
    """执行错误处理与DLQ示例。"""
    if DB_FILE.exists():
        DB_FILE.unlink()

    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE.resolve()}",
        source_lang="en",
        active_engine=EngineName.DEBUG,
        retry_policy=RetryPolicyConfig(max_attempts=1, initial_backoff=0.1),
        engine_configs={
            "debug": {
                "fail_on_text": FAILING_TEXT,
                "fail_is_retryable": True,
            }
        },
    )
    apply_migrations(config.db_path)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()
        log.info("✅ 协调器初始化成功", db_path=str(DB_FILE))

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
        # v3.7 优化：自动化验证，不再需要手动查询
        await verify_dlq_entry()
        log.info("🎉 验证通过！任务已成功进入死信队列。")

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


async def verify_dlq_entry() -> None:
    """连接数据库并验证死信队列中是否存在记录。"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM th_dead_letter_queue")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 1


if __name__ == "__main__":
    # 动态导入并配置日志，以避免在导入时产生副作用
    from trans_hub.logging_config import setup_logging
    setup_logging(log_level="INFO")
    asyncio.run(main())
