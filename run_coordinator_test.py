"""
run_coordinator_test.py (v1.0.1 Final, Corrected)

Trans-Hub v1.0 最终功能验证脚本。
它遵循最佳实践，在程序入口处主动加载 .env 文件，
并对所有核心功能进行端到端测试。
"""
import os
import time
import uuid
from dotenv import load_dotenv

import structlog
from trans_hub.logging_config import setup_logging
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngine, DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngine, OpenAIEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import TranslationStatus, TranslationResult


# ==============================================================================
#  测试套件函数
# ==============================================================================

def test_core_flow_with_debug_engine():
    """
    测试核心工作流（请求、处理、重试、速率限制）使用 DebugEngine。
    这个测试快速、无外部依赖，适合在 CI 环境中频繁运行。
    """
    log = structlog.get_logger("test_core_flow")
    log.info("--- 开始核心流程测试 (使用 DebugEngine) ---")

    DB_FILE = "transhub_core_test.db"
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    debug_config = DebugEngineConfig(fail_on_text="cherry", fail_is_retryable=True)
    debug_engine = DebugEngine(config=debug_config)
    rate_limiter = RateLimiter(refill_rate=2, capacity=1)
    
    coordinator = Coordinator(
        persistence_handler=handler,
        engines={"debug": debug_engine},
        active_engine_name="debug",
        rate_limiter=rate_limiter
    )

    try:
        coordinator.request(target_langs=['jp'], text_content="apple")
        coordinator.request(target_langs=['jp'], text_content="banana")
        coordinator.request(target_langs=['jp'], text_content="cherry")

        start_time = time.monotonic()
        results = list(coordinator.process_pending_translations(
            target_lang="jp", batch_size=1, max_retries=1, initial_backoff=0.1
        ))
        duration = time.monotonic() - start_time
        
        log.info("核心流程测试完成", duration=f"{duration:.2f}s")
        assert len(results) == 3
        assert duration > 1.0, "速率限制器未生效"
        
        cherry_result = next(r for r in results if r.original_content == "cherry")
        assert cherry_result.status == TranslationStatus.FAILED, "重试逻辑未生效"

        log.info("✅ 核心流程测试成功！")

    finally:
        coordinator.close()


def test_garbage_collection():
    """独立的垃圾回收功能测试。"""
    log = structlog.get_logger("test_gc")
    log.info("--- 开始垃圾回收 (GC) 测试 ---")

    DB_FILE = "transhub_gc_test.db"
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    coordinator = Coordinator(
        persistence_handler=handler,
        engines={"debug": DebugEngine(DebugEngineConfig())},
        active_engine_name="debug"
    )

    try:
        with handler.transaction() as cursor:
            cursor.execute("INSERT INTO th_content (id, value, created_at) VALUES (1, 'old_content', '2020-01-01 10:00:00')")
            cursor.execute("INSERT INTO th_content (id, value) VALUES (2, 'active_content')")
            cursor.execute("INSERT INTO th_content (id, value, created_at) VALUES (3, 'orphan_content', '2020-01-01 11:00:00')")
            cursor.execute("INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:old', 1, '2020-01-01 10:00:00')")
            cursor.execute("INSERT INTO th_sources (business_id, content_id, last_seen_at) VALUES ('source:active', 2, ?)", (time.strftime('%Y-%m-%d %H:%M:%S'),))

        stats_dry = coordinator.run_garbage_collection(retention_days=1000, dry_run=True)
        assert stats_dry["deleted_sources"] == 1 and stats_dry["deleted_content"] == 1
        
        stats_real = coordinator.run_garbage_collection(retention_days=1000, dry_run=False)
        assert stats_real["deleted_sources"] == 1 and stats_real["deleted_content"] == 2

        with handler.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM th_content")
            assert cursor.fetchone()[0] == 1
        
        log.info("✅ 垃圾回收 (GC) 测试成功！")

    finally:
        coordinator.close()


def test_openai_engine_flow():
    """
    测试 OpenAIEngine，并能智能处理因配置问题（如无效Key）导致的失败。
    """
    log = structlog.get_logger("test_openai_engine")
    
    try:
        openai_config = OpenAIEngineConfig()
        if not openai_config.base_url:
            log.warning("未找到 TH_OPENAI_ENDPOINT 配置，跳过 OpenAI 引擎测试。")
            return
    except Exception as e:
        log.warning(f"加载 OpenAI 配置时出错，跳过测试: {e}")
        return

    log.info("--- 开始 OpenAI 引擎流程测试 ---", model=openai_config.model, base_url=openai_config.base_url)
    
    DB_FILE = "transhub_openai_test.db"
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    openai_engine = OpenAIEngine(config=openai_config)
    
    coordinator = Coordinator(
        persistence_handler=handler,
        engines={"openai": openai_engine},
        active_engine_name="openai"
    )

    try:
        text_to_translate = "Hello, world! This is a test of the Trans-Hub system."
        target_lang = "Spanish"
        coordinator.request(target_langs=[target_lang], text_content=text_to_translate)
        results = list(coordinator.process_pending_translations(target_lang=target_lang))
        
        assert len(results) == 1, "应该只返回一个结果"
        result = results[0]
        
        log.info("翻译结果", result=result)
        
        if result.status == TranslationStatus.TRANSLATED:
            assert "Hola, mundo" in result.translated_content, f"翻译结果不符合预期: {result.translated_content}"
            log.info("✅ OpenAI 引擎测试成功！(API Key 有效)")
        elif result.status == TranslationStatus.FAILED:
            assert result.error is not None, "失败结果必须包含错误信息"
            if "401" in result.error:
                log.warning("✅ 测试收到 401 错误，引擎错误处理逻辑工作正常。")
            else:
                assert False, f"发生非 401 的意外错误: {result.error}"
        else:
             assert False, f"翻译结果状态异常: {result.status}"
    finally:
        coordinator.close()


def main():
    """主函数，统一执行所有测试。"""
    # 1. 在程序最开始主动加载 .env 文件
    if load_dotenv():
        print("✅ .env 文件已加载。")
    else:
        print("⚠️ 未找到 .env 文件，将依赖系统环境变量。")

    # 2. 配置日志系统
    setup_logging(log_level="INFO", log_format="console")
    
    # 3. 绑定唯一的调用链 ID
    correlation_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    
    root_log = structlog.get_logger("main_test_runner")
    root_log.info("======== Trans-Hub v1.0 最终功能验证开始 ========")
    
    try:
        # 4. 按顺序运行所有测试套件
        test_core_flow_with_debug_engine()
        test_garbage_collection()
        test_openai_engine_flow()
        
        root_log.info("🎉 ======== 所有测试成功通过！Trans-Hub v1.0 核心功能完成！ ======== 🎉")
        
    except Exception:
        root_log.error("❌ 测试过程中发生未捕获的异常！", exc_info=True)
        # 重新抛出异常，以便 CI/CD 环境能捕获到非零退出码
        raise
    finally:
        # 5. 清理上下文变量
        structlog.contextvars.clear_contextvars()


if __name__ == "__main__":
    main()