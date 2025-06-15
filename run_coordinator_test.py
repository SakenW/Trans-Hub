# run_coordinator_test.py
"""
Trans-Hub 核心功能端到端测试脚本。

本脚本旨在验证 Coordinator 是否能与所有核心翻译引擎（Debug, Translators, OpenAI）
正确协同工作，并覆盖主要的业务流程，如请求、处理、缓存和垃圾回收。
"""

import datetime
import os
import shutil
from typing import Any, Optional

import structlog
from dotenv import load_dotenv

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.debug import DebugEngineConfig
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationStatus

try:
    from trans_hub.engines.translators_engine import TranslatorsEngineConfig
except ModuleNotFoundError:
    from trans_hub.engines.translators import TranslatorsEngineConfig

log = structlog.get_logger()

TEST_DIR = "temp_test_data"


def setup_test_environment(db_name: str) -> str:
    """为单个测试创建一个干净的子目录和数据库，并返回数据库路径。"""
    test_subdir = os.path.join(TEST_DIR, db_name.replace(".db", ""))
    if os.path.exists(test_subdir):
        shutil.rmtree(test_subdir)
    os.makedirs(test_subdir)

    db_path = os.path.join(test_subdir, db_name)
    apply_migrations(db_path)
    log.info(f"测试环境 '{test_subdir}' 已准备就绪。")
    return db_path


def cleanup_test_environment():
    """在所有测试完成后，清理整个临时测试目录。"""
    log.info("--- 正在清理所有测试环境 ---")
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    log.info("所有测试环境已清理完毕。")


def run_engine_test(
    engine_name: str,
    engine_config_instance: Any,
    db_path: str,
    text_to_translate: str,
    target_lang: str,
    context: Optional[dict[str, Any]] = None,
    source_lang: Optional[str] = None,
):
    """一个通用的引擎测试函数，执行完整的翻译和缓存验证流程。"""
    log.info(f"\n--- 开始测试引擎: {engine_name.upper()} ---")

    # 核心修复: 在创建 TransHubConfig 时传入 source_lang
    config = TransHubConfig(
        active_engine=engine_name,
        engine_configs=EngineConfigs(**{engine_name: engine_config_instance}),
        source_lang=source_lang,  # 将源语言设为全局配置
    )
    handler = DefaultPersistenceHandler(db_path=db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        # --- 第一次翻译：执行实际 API 调用 ---
        log.info("第一次翻译（应该触发 API 调用）...")
        coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=f"test.{engine_name}.greeting",
            context=context,
            # source_lang 参数从 request 调用中移除，因为它现在是全局配置
        )

        results = list(
            coordinator.process_pending_translations(target_lang=target_lang)
        )

        # 断言结果
        assert len(results) == 1, f"[{engine_name}] 应该返回一个结果"
        result = results[0]

        if result.status != TranslationStatus.TRANSLATED:
            error_msg = result.error or "未知错误"
            raise AssertionError(
                f"[{engine_name}] 翻译状态应为 TRANSLATED，但实际为 {result.status.name}。"
                f" 错误信息: {error_msg}"
            )

        assert (
            result.engine == engine_name
        ), f"[{engine_name}] 引擎名称应为 '{engine_name}'"
        assert result.translated_content, f"[{engine_name}] 翻译内容不应为空"
        log.info(
            f"[{engine_name}] 翻译成功",
            原始文本=result.original_content,
            翻译结果=result.translated_content,
        )

        # --- 第二次翻译：验证缓存 ---
        log.info("第二次翻译（应该命中缓存）...")
        coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=f"test.{engine_name}.greeting",
            context=context,
        )

        cached_results = list(
            coordinator.process_pending_translations(target_lang=target_lang)
        )
        assert (
            len(cached_results) == 0
        ), f"[{engine_name}] 第二次调用不应处理任何新任务，因为已缓存"
        log.info(f"[{engine_name}] 缓存验证成功。")

        log.info(f"✅ 引擎测试成功: {engine_name.upper()}")

    finally:
        if coordinator:
            coordinator.close()


def test_gc_workflow(db_path: str):
    """一个专注、健壮的垃圾回收 (GC) 测试函数。"""
    log.info("\n--- 开始测试垃圾回收 (GC) ---")

    handler = DefaultPersistenceHandler(db_path=db_path)
    config = TransHubConfig(
        active_engine="debug",
        engine_configs=EngineConfigs(debug=DebugEngineConfig()),
        gc_retention_days=1,
    )
    coordinator = Coordinator(config=config, persistence_handler=handler)

    try:
        coordinator.request(
            target_langs=["ja"], text_content="active item", business_id="active.item"
        )
        coordinator.request(
            target_langs=["ja"], text_content="legacy item", business_id="legacy.item"
        )
        list(coordinator.process_pending_translations(target_lang="ja"))
        log.info("初始数据已创建并翻译。")

        past_datetime = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(days=2)
        with handler.transaction() as cursor:
            cursor.execute(
                "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
                (past_datetime.isoformat(), "legacy.item"),
            )
        log.info("'legacy.item' 的时间戳已更新为两天前。")

        dry_run_stats = coordinator.run_garbage_collection(dry_run=True)
        assert (
            dry_run_stats["deleted_sources"] == 1
        ), "[GC 干跑] GC 应该能识别出1个待清理的源"
        log.info("[GC 干跑] 验证成功。")

        actual_gc_stats = coordinator.run_garbage_collection(dry_run=False)
        assert (
            actual_gc_stats["deleted_sources"] == 1
        ), "[GC 实际执行] GC 应该实际清理了1个过时的源"

        with handler.transaction() as cursor:
            cursor.execute("SELECT business_id FROM th_sources")
            remaining_bids = {row[0] for row in cursor.fetchall()}
            assert remaining_bids == {
                "active.item"
            }, "[GC 实际执行] GC后应只剩下 'active.item'"

        log.info("✅ 垃圾回收 (GC) 测试成功！")

    finally:
        if coordinator:
            coordinator.close()


def main():
    """运行所有测试套件。"""
    load_dotenv()
    setup_logging(log_level="INFO")
    root_log = structlog.get_logger("测试运行器")

    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR)

    try:
        root_log.info("======== Trans-Hub v1.1.1 功能验证开始 ========")

        # === 测试套件 1: Debug 引擎 ===
        db_path_debug = setup_test_environment("debug_test.db")
        run_engine_test(
            engine_name="debug",
            engine_config_instance=DebugEngineConfig(),
            db_path=db_path_debug,
            text_to_translate="一个简单的测试。",
            target_lang="dbg",
        )

        # === 测试套件 2: Translators 引擎 (免费，无需配置) ===
        db_path_translators = setup_test_environment("translators_test.db")
        run_engine_test(
            engine_name="translators",
            engine_config_instance=TranslatorsEngineConfig(provider="google"),
            db_path=db_path_translators,
            text_to_translate="The quick brown fox jumps over the lazy dog.",
            target_lang="zh-CN",
        )

        # === 测试套件 3: OpenAI 引擎 (需要配置) ===
        openai_api_key = os.getenv("TH_OPENAI_API_KEY")
        if (
            openai_api_key
            and openai_api_key != "your-secret-key"
            and openai_api_key.strip() != ""
        ):
            db_path_openai = setup_test_environment("openai_test.db")
            run_engine_test(
                engine_name="openai",
                engine_config_instance=OpenAIEngineConfig(),
                db_path=db_path_openai,
                text_to_translate="The art of programming is the skill of controlling complexity.",
                target_lang="fr",
                source_lang="en",  # OpenAI 引擎需要源语言
            )
        else:
            root_log.warning(
                "跳过 OpenAI 引擎测试：环境变量或 .env 文件中未配置 TH_OPENAI_API_KEY。",
                原因="缺少配置",
            )

        # === 测试套件 4: 垃圾回收 (GC) ===
        db_path_gc = setup_test_environment("gc_test.db")
        test_gc_workflow(db_path=db_path_gc)

        root_log.info(
            "🎉======== 所有测试成功通过！Trans-Hub v1.1.1 功能验证完成！========🎉"
        )

    except Exception:
        root_log.error("❌ 测试过程中发生未捕获的异常！", exc_info=True)
        raise
    finally:
        cleanup_test_environment()


if __name__ == "__main__":
    main()
