import os
import time
import uuid

import structlog
from dotenv import load_dotenv

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import TranslationStatus


def test_rate_limiter():
    log = structlog.get_logger("test_rate_limiter")
    log.info("--- 开始速率限制器功能测试 ---")
    db_file = "transhub_ratelimit_test.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    apply_migrations(db_file)
    handler = DefaultPersistenceHandler(db_path=db_file)
    rate_limiter = RateLimiter(refill_rate=2, capacity=1)
    config = TransHubConfig(
        database_url=f"sqlite:///{db_file}",
        active_engine="debug",
        engine_configs=EngineConfigs(debug=DebugEngineConfig()),
    )
    coordinator = Coordinator(
        config=config, persistence_handler=handler, rate_limiter=rate_limiter
    )
    try:
        coordinator.request(target_langs=["jp"], text_content="a")
        coordinator.request(target_langs=["jp"], text_content="b")
        coordinator.request(target_langs=["jp"], text_content="c")
        start_time = time.monotonic()
        results = list(
            coordinator.process_pending_translations(
                target_lang="jp", batch_size=1, max_retries=0
            )
        )
        duration = time.monotonic() - start_time
        log.info("速率限制测试完成", duration=f"{duration:.2f}s")
        assert len(results) == 3
        assert duration > 0.95, f"速率限制器未生效 (duration: {duration:.2f}s)"
        log.info("✅ 速率限制器测试成功！")
    finally:
        coordinator.close()


def test_retry_logic():
    log = structlog.get_logger("test_retry_logic")
    log.info("--- 开始重试逻辑测试 ---")
    db_file = "transhub_retry_test.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    apply_migrations(db_file)
    handler = DefaultPersistenceHandler(db_path=db_file)
    debug_config_with_failure = DebugEngineConfig(
        fail_on_text="cherry", fail_is_retryable=True
    )
    config = TransHubConfig(
        database_url=f"sqlite:///{db_file}",
        active_engine="debug",
        engine_configs=EngineConfigs(debug=debug_config_with_failure),
    )
    coordinator = Coordinator(config=config, persistence_handler=handler)
    try:
        coordinator.request(target_langs=["jp"], text_content="apple")
        coordinator.request(target_langs=["jp"], text_content="cherry")
        results = list(
            coordinator.process_pending_translations(
                target_lang="jp", max_retries=1, initial_backoff=0.1
            )
        )
        log.info("重试逻辑测试完成", results_count=len(results))
        cherry_result = next(r for r in results if r.original_content == "cherry")
        assert cherry_result.status == TranslationStatus.FAILED
        log.info("✅ 重试逻辑测试成功！")
    finally:
        coordinator.close()


def test_garbage_collection():
    log = structlog.get_logger("test_gc")
    log.info("--- 开始垃圾回收 (GC) 测试 ---")
    db_file = "transhub_gc_test.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    apply_migrations(db_file)
    handler = DefaultPersistenceHandler(db_path=db_file)
    config = TransHubConfig(
        database_url=f"sqlite:///{db_file}",
        active_engine="debug",
        engine_configs=EngineConfigs(),
    )
    coordinator = Coordinator(config=config, persistence_handler=handler)
    try:
        with handler.transaction() as cursor:
            cursor.execute(
                "INSERT INTO th_content (id, value, created_at) VALUES (1, 'old_content', '2020-01-01 10:00:00')"
            )
            cursor.execute(
                "INSERT INTO th_content (id, value) VALUES (2, 'active_content')"
            )
            cursor.execute(
                "INSERT INTO th_content (id, value, created_at) VALUES (3, 'orphan_content', '2020-01-01 11:00:00')"
            )
            cursor.execute(
                "INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:old', 1, '2020-01-01 10:00:00')"
            )
            cursor.execute(
                "INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:active', 2, ?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"),),
            )
        stats_dry = coordinator.run_garbage_collection(
            retention_days=1000, dry_run=True
        )
        assert stats_dry["deleted_sources"] == 1 and stats_dry["deleted_content"] == 1
        stats_real = coordinator.run_garbage_collection(
            retention_days=1000, dry_run=False
        )
        assert stats_real["deleted_sources"] == 1 and stats_real["deleted_content"] == 2
        with handler.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM th_content")
            assert cursor.fetchone()[0] == 1
        log.info("✅ 垃圾回收 (GC) 测试成功！")
    finally:
        coordinator.close()


def test_openai_engine_flow():
    log = structlog.get_logger("test_openai_engine")
    if "openai" not in ENGINE_REGISTRY:
        log.warning("OpenAI 引擎未被加载，跳过测试。")
        return
    log.info("--- 开始 OpenAI 引擎流程测试 ---")
    db_file = "transhub_openai_test.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    apply_migrations(db_file)
    handler = DefaultPersistenceHandler(db_path=db_file)
    try:
        config = TransHubConfig(
            database_url=f"sqlite:///{db_file}",
            active_engine="openai",
            engine_configs=EngineConfigs(openai=OpenAIEngineConfig()),
        )
        if not config.engine_configs.openai.base_url:
            log.warning("未找到 TH_OPENAI_ENDPOINT 配置，跳过 OpenAI 引擎测试。")
            return
    except Exception as e:
        log.warning("加载或验证 OpenAI 配置时出错，跳过测试", error=str(e))
        return
    coordinator = Coordinator(config=config, persistence_handler=handler)
    try:
        text_to_translate = "Hello, world!"
        target_lang = "Spanish"
        coordinator.request(target_langs=[target_lang], text_content=text_to_translate)
        results = list(
            coordinator.process_pending_translations(target_lang=target_lang)
        )
        assert len(results) == 1
        result = results[0]
        log.info("翻译结果", result=result)
        if result.status == TranslationStatus.TRANSLATED:
            assert "Hola, mundo" in result.translated_content
            log.info("✅ OpenAI 引擎测试成功！(API Key 有效)")
        elif result.status == TranslationStatus.FAILED:
            assert result.error is not None
            if "401" in result.error:
                log.warning("✅ 测试收到 401 错误，引擎错误处理逻辑工作正常。")
            else:
                raise AssertionError(f"发生非 401 的意外错误: {result.error}")
        else:
            raise AssertionError(f"翻译结果状态异常: {result.status}")
    finally:
        coordinator.close()


def main():
    if load_dotenv():
        print("✅ .env 文件已加载。")
    else:
        print("⚠️ 未找到 .env 文件。")
    setup_logging(log_level="INFO", log_format="console")
    correlation_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    root_log = structlog.get_logger("main_test_runner")
    root_log.info("======== Trans-Hub v1.0 最终功能验证开始 ========")
    try:
        test_rate_limiter()
        test_retry_logic()
        test_garbage_collection()
        test_openai_engine_flow()
        root_log.info("🎉 ======== 所有测试成功通过！Trans-Hub v1.0 核心功能完成！ ======== 🎉")
    except Exception:
        root_log.error("❌ 测试过程中发生未捕获的异常！", exc_info=True)
        raise
    finally:
        structlog.contextvars.clear_contextvars()


if __name__ == "__main__":
    main()
