# examples/demo_complex_workflow.py
"""
一个复杂异步工作流的端到端演示。

本脚本将展示 Trans-Hub 的所有核心高级功能，包括：
- 动态引擎激活 (OpenAI)
- 上下文相关的翻译 (使用'Jaguar'作为示例)
- 持久化缓存与 `touch_source`
- 可靠的、确定性的垃圾回收 (GC) 演示

运行方式:
1. 确保在项目根目录的 .env 文件中已配置 TH_OPENAI_API_KEY 和 TH_OPENAI_MODEL (推荐 gpt-4o)。
2. 在项目根目录执行 `poetry run python examples/demo_complex_workflow.py`
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import structlog
from dotenv import load_dotenv

# -- 路径设置 --
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import (  # noqa: E402
    Coordinator,
    DefaultPersistenceHandler,
    TransHubConfig,
    TranslationStatus,
)
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

# --- 演示配置 ---
DB_FILE_PATH = PROJECT_ROOT / "complex_demo.db"
log = structlog.get_logger()


def generate_context_for_text(text: str, category: str = "") -> dict:
    """根据文本和类别动态生成上下文。"""
    context = {"source": "demo_workflow"}
    if category:
        context["category"] = category
        context["system_prompt"] = (
            f"You are a professional translator specializing in '{category}'. Provide only the translated text, without quotes."
        )
    else:
        context["system_prompt"] = (
            "You are a professional, general-purpose translator. Provide only the translated text, without quotes."
        )
    return context


async def initialize_trans_hub() -> Coordinator:
    """一个标准的异步初始化函数，返回一个配置好的 Coordinator 实例。"""
    DB_FILE_PATH.unlink(missing_ok=True)
    log.info("旧数据库已清理。")

    log.info("正在应用数据库迁移...", db_path=str(DB_FILE_PATH))
    apply_migrations(str(DB_FILE_PATH))

    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE_PATH.resolve()}",
        active_engine="openai",
        source_lang="en",
    )

    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()
    return coordinator


async def request_and_process(
    coordinator: Coordinator, tasks: list[dict], target_lang: str
):
    """辅助函数：登记任务并处理它们。"""
    log.info(f"\n---> 开始登记 {len(tasks)} 个任务到 '{target_lang}' <---")

    for task in tasks:
        context = generate_context_for_text(task["text"], task.get("category", ""))
        await coordinator.request(
            target_langs=[target_lang],
            text_content=task["text"],
            context=context,
            business_id=task.get("business_id"),
        )
    log.info("所有任务登记完成。")

    log.info(f"---> 正在处理所有待翻译任务到 '{target_lang}' <---")
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    if results:
        for result in results:
            if result.status == TranslationStatus.TRANSLATED:
                log.info(
                    "✅ 翻译成功",
                    original=result.original_content,
                    translated=result.translated_content,
                    biz_id=result.business_id,
                )
            else:
                log.error("❌ 翻译失败", result=result)
    else:
        log.warning("🟡 没有需要处理的新任务（缓存命中）。")
    log.info("-" * 80)


async def main():
    """主程序入口：复杂异步工作流演示。"""
    setup_logging(log_level="INFO")
    load_dotenv()

    coordinator = None
    try:
        coordinator = await initialize_trans_hub()
        zh = "zh-CN"
        fr = "fr"

        log.info("=" * 30 + " 阶段 1: 首次翻译与上下文 " + "=" * 30)
        initial_tasks = [
            {
                "text": "Jaguar",
                "category": "animal",
                "business_id": "wildlife.big_cat.jaguar",
            },
            {
                "text": "Jaguar",
                "category": "car brand",
                "business_id": "automotive.brand.jaguar",
            },
            {
                "text": "Legacy text to be deleted",
                "business_id": "legacy.feature.old_text",
            },
        ]
        await request_and_process(coordinator, initial_tasks, zh)

        log.info("=" * 30 + " 阶段 2: 缓存命中与来源更新 " + "=" * 30)
        log.info("将重新请求 'Jaguar' (animal)，以更新其 last_seen_at 时间戳。")
        tasks_to_touch = [
            {
                "text": "Jaguar",
                "category": "animal",
                "business_id": "wildlife.big_cat.jaguar",
            }
        ]
        await request_and_process(coordinator, tasks_to_touch, zh)
        log.info(
            "'automotive.brand.jaguar' 和 'legacy.feature.old_text' 没有被重新请求。"
        )

        log.info("为了可靠地演示GC，我们将手动更新数据库中的时间戳。")
        async with aiosqlite.connect(DB_FILE_PATH) as db:
            two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            await db.execute(
                "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
                (two_days_ago, "automotive.brand.jaguar"),
            )
            await db.execute(
                "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?",
                (two_days_ago, "legacy.feature.old_text"),
            )
            await db.commit()
        log.info("已将2个源记录的时间戳手动设置为2天前。")

        log.info("=" * 30 + " 阶段 3: 新任务与多语言 " + "=" * 30)
        new_tasks = [
            {
                "text": "Welcome to our new platform!",
                "business_id": "ui.onboarding.welcome",
            },
            {"text": "Translate me to French!", "business_id": "test.new.french_text"},
        ]
        await request_and_process(coordinator, new_tasks[:1], zh)
        await request_and_process(coordinator, new_tasks[1:], fr)

        log.info("=" * 30 + " 阶段 4: 垃圾回收 " + "=" * 30)
        log.info("我们将使用 expiration_days=1，清理掉所有超过1天未被'touch'的记录。")
        log.info(
            "预计 'automotive.brand.jaguar' 和 'legacy.feature.old_text' 将被删除。"
        )
        gc_report = await coordinator.run_garbage_collection(
            dry_run=True, expiration_days=1
        )
        log.info("GC 干跑报告", report=gc_report)
        await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
        log.info("GC 已实际执行。")
        gc_report_after = await coordinator.run_garbage_collection(
            dry_run=True, expiration_days=1
        )
        log.info("GC 第二次干跑报告", report=gc_report_after)
        if gc_report_after.get("deleted_sources", 0) == 0:
            log.info("✅ 成功！第二次干跑没有发现可清理的源，符合预期。")

    except Exception as e:
        log.error("演示工作流发生意外错误", error=str(e), exc_info=True)
    finally:
        if coordinator:
            await coordinator.close()
            log.info("Trans-Hub 协调器已关闭。")
            log.info("临时数据库已保留，请使用以下命令检查内容：")
            relative_db_path = DB_FILE_PATH.relative_to(PROJECT_ROOT)
            print(f"\npoetry run python tools/inspect_db.py {relative_db_path}\n")


if __name__ == "__main__":
    asyncio.run(main())
