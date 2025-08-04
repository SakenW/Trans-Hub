# examples/04_error_handling_and_dlq.py
"""
Trans-Hub v3.0 错误处理与死信队列(DLQ)示例

本示例展示了系统如何处理持久性失败的任务：
1. 配置 Debug 引擎，使其对特定文本总是返回失败。
2. 配置 Coordinator 的重试策略为一个较小的值。
3. 提交一个注定会失败的翻译请求。
4. 启动 Worker，观察任务在重试后最终失败。
5. (需要手动检查数据库) 验证失败的任务已被移入 `th_dead_letter_queue` 表。
"""
import asyncio
import os
import sys
from pathlib import Path

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, EngineName, TransHubConfig  # noqa: E402
from trans_hub.config import RetryPolicyConfig  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger(__name__)

# --- 准备测试环境 ---
DB_FILE = "th_example_04.db"
FAILING_TEXT = "This will always fail"


async def main() -> None:
    """执行错误处理与DLQ示例。"""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    # 1. 自定义配置
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        source_lang="en",
        active_engine=EngineName.DEBUG,
        # 配置重试策略：最多1次重试，初始退避0.1秒
        retry_policy=RetryPolicyConfig(max_attempts=1, initial_backoff=0.1),
        engine_configs={
            "debug": {
                # 配置Debug引擎：对特定文本返回不可重试的失败
                "fail_on_text": FAILING_TEXT,
                "fail_is_retryable": True,  # 设置为True以触发重试逻辑
            }
        },
    )
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        await coordinator.initialize()

        business_id = "task.that.fails"
        source_payload = {"text": FAILING_TEXT}
        target_lang = "de"

        # 2. 提交注定失败的任务
        log.info("🚀 步骤 1: 提交一个注定会失败的任务...")
        await coordinator.request(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=[target_lang],
        )

        # 3. 启动 Worker 处理
        log.info("👷 步骤 2: Worker 开始处理，预期会看到重试和最终失败日志...")
        results = [
            res async for res in coordinator.process_pending_translations(target_lang)
        ]
        
        # 4. 验证结果
        log.info("🔍 步骤 3: 检查 Worker 的处理结果...")
        if not results:
             log.warning("Worker 未返回结果，这可能是因为任务已移至DLQ。")
        else:
             log.info("Worker 返回的结果", results=results)


        log.info(
            "✅ 示例执行完毕。请使用 `sqlite3 th_example_04.db 'SELECT * FROM th_dead_letter_queue;'` "
            "来验证任务是否已进入死信队列。"
        )

    finally:
        await coordinator.close()
        # 保留数据库文件以供检查
        # if os.path.exists(DB_FILE):
        #     os.remove(DB_FILE)


if __name__ == "__main__":
    asyncio.run(main())