# run_coordinator_test.py (v1.1 最终版)
import os
import shutil
import time
from typing import Any, Dict, List

import structlog

# 第三方库导入
from dotenv import load_dotenv

# 本地库导入
from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import TranslationStatus

# 获取一个 logger
log = structlog.get_logger()

# 定义一个临时的测试目录和数据库文件
TEST_DIR = "temp_test_data"
DB_FILE = os.path.join(TEST_DIR, "test_transhub.db")


def setup_test_environment():
    """创建一个干净的测试环境。"""
    log.info("--- 正在设置测试环境 ---")
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)
    apply_migrations(DB_FILE)
    log.info("测试环境已就绪。")


def cleanup_test_environment():
    """清理测试环境。"""
    log.info("--- 正在清理测试环境 ---")
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    log.info("测试环境已清理。")


def test_full_workflow():
    """
    测试 Trans-Hub 的完整端到端工作流，包括：
    1. 首次翻译与缓存。
    2. 上下文翻译。
    3. 错误处理与重试。
    4. 速率限制。
    5. 垃圾回收 (GC)。
    """
    log.info("====== 开始 Trans-Hub v1.1 完整工作流测试 ======")

    # --- 1. 初始化 Coordinator ---
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    # 使用 DebugEngine 进行可预测的测试
    debug_config = DebugEngineConfig(
        mode="SUCCESS",
        translation_map={
            "Hello, world!": "你好，调试世界！",
            "Apple": "苹果 (水果上下文)",
            "Bank": "银行 (金融上下文)",
        },
        # 配置一个可重试的失败场景
        fail_on_text="retry_me",
        fail_is_retryable=True,
    )
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        active_engine="debug",
        engine_configs=EngineConfigs(debug=debug_config),
        gc_retention_days=0,  # 设置为0天，方便测试GC
    )
    # 配置一个速率限制器，每秒2个请求
    rate_limiter = RateLimiter(rate=2, capacity=2)
    coordinator = Coordinator(
        config=config, persistence_handler=handler, rate_limiter=rate_limiter
    )

    try:
        # --- 2. 测试首次翻译与上下文 ---
        log.info("\n--- 测试阶段：首次翻译与上下文 ---")
        tasks_to_request: List[Dict[str, Any]] = [
            {"text": "Hello, world!", "context": None, "business_id": "greeting.hello"},
            {
                "text": "Apple",
                "context": {"category": "fruit"},
                "business_id": "food.apple",
            },
            {
                "text": "Bank",
                "context": {"type": "financial_institution"},
                "business_id": "finance.bank",
            },
            {
                "text": "This item will be garbage collected",
                "context": None,
                "business_id": "legacy.item",
            },
        ]
        for task in tasks_to_request:
            coordinator.request(
                target_langs=["jp"],
                text_content=task["text"],
                context=task["context"],
                business_id=task["business_id"],
            )

        results = list(coordinator.process_pending_translations(target_lang="jp"))
        assert len(results) == 4
        log.info("✅ 首次翻译与上下文测试成功！")

        # --- 3. 测试缓存 ---
        log.info("\n--- 测试阶段：缓存命中 ---")
        # 再次请求，这次不应该有任何新任务被处理
        coordinator.request(
            target_langs=["jp"],
            text_content="Hello, world!",
            business_id="greeting.hello",
        )
        cached_run_results = list(
            coordinator.process_pending_translations(target_lang="jp")
        )
        assert (
            len(cached_run_results) == 0
        ), "缓存命中时，process_pending_translations 不应返回任何结果"
        # 直接查询缓存进行验证
        cached_result = coordinator.handler.get_translation("Hello, world!", "jp")
        assert cached_result is not None and cached_result.from_cache is True
        log.info("✅ 缓存命中测试成功！")

        # --- 4. 测试错误处理与重试 ---
        log.info("\n--- 测试阶段：错误处理与重试 ---")
        coordinator.request(
            target_langs=["jp"], text_content="retry_me", business_id="test.retry"
        )
        # 配置 DebugEngine 在下一次调用时成功
        coordinator.active_engine.config.fail_on_text = None

        retry_results = list(
            coordinator.process_pending_translations(
                target_lang="jp", max_retries=1, initial_backoff=0.1
            )
        )
        assert (
            len(retry_results) == 1
            and retry_results[0].status == TranslationStatus.TRANSLATED
        )
        log.info("✅ 错误处理与重试测试成功！")

        # --- 5. 测试速率限制 ---
        log.info("\n--- 测试阶段：速率限制 ---")
        # 创建3个新任务，batch_size=1, 速率为2/s，至少需要0.5秒
        rate_limit_tasks = [
            {"text": "rate_1", "business_id": "rate.1"},
            {"text": "rate_2", "business_id": "rate.2"},
            {"text": "rate_3", "business_id": "rate.3"},
        ]
        for task in rate_limit_tasks:
            coordinator.request(
                target_langs=["jp"],
                text_content=task["text"],
                business_id=task["business_id"],
            )

        start_time = time.monotonic()
        rate_limit_results = list(
            coordinator.process_pending_translations(target_lang="jp", batch_size=1)
        )
        duration = time.monotonic() - start_time
        assert len(rate_limit_results) == 3
        assert duration > 0.45, f"速率限制器未生效 (duration: {duration:.2f}s)"
        log.info(f"✅ 速率限制测试成功！(耗时: {duration:.2f}s)")

        # --- 6. 测试垃圾回收 ---
        log.info("\n--- 测试阶段：垃圾回收 (GC) ---")
        # 'legacy.item' business_id 在此之后没有被再次 request
        # 我们只更新了 'greeting.hello', 'test.retry', 和 rate.* 的 last_seen_at
        gc_stats_dry = coordinator.run_garbage_collection(dry_run=True)
        # 预估将清理 food.apple 和 finance.bank 以及 legacy.item
        # 因为它们在第3步之后没有被再次 request
        assert gc_stats_dry["deleted_sources"] == 3, "GC dry_run 应该预估清理3个过时的源"

        gc_stats_real = coordinator.run_garbage_collection(dry_run=False)
        assert gc_stats_real["deleted_sources"] == 3, "GC 应该实际清理了3个过时的源"

        with handler.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM th_sources")
            # 剩下 'greeting.hello', 'test.retry', 和3个rate.* 的源，共5个
            remaining_sources = cursor.fetchone()[0]
            assert remaining_sources == 5, f"GC后应剩下5个源，实际为{remaining_sources}"
        log.info("✅ 垃圾回收 (GC) 测试成功！")

    finally:
        if coordinator:
            coordinator.close()


def main():
    """运行所有测试。"""
    load_dotenv()
    setup_logging(log_level="INFO")

    root_log = structlog.get_logger("test_runner")
    root_log.info("======== Trans-Hub v1.1 功能验证开始 ========")

    try:
        setup_test_environment()
        test_full_workflow()
        root_log.info("🎉======== 所有测试成功通过！Trans-Hub v1.1 功能验证完成！========🎉")
    except Exception:
        root_log.error("❌ 测试过程中发生未捕获的异常！", exc_info=True)
        raise
    finally:
        cleanup_test_environment()


if __name__ == "__main__":
    main()
