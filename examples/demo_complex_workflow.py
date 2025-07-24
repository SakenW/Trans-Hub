# examples/demo_complex_workflow.py (终极无误版)
import asyncio
import os

import structlog
from dotenv import load_dotenv

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

log = structlog.get_logger(__name__)

# --- 核心修正 1：将数据库文件定义在示例文件旁边，并获取其绝对路径 ---
EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE_PATH = os.path.join(EXAMPLES_DIR, "complex_demo.db")
GC_RETENTION_DAYS = 0


async def initialize_trans_hub(db_path: str, gc_retention_days: int) -> Coordinator:
    """一个标准的异步初始化函数，返回一个配置好的 Coordinator 实例。."""
    if os.path.exists(db_path):
        os.remove(db_path)

    log.info("数据库不存在，正在创建并迁移...", db_path=db_path)
    apply_migrations(db_path)

    # --- 核心修正 2：确保 database_url 使用的是绝对路径 ---
    config = TransHubConfig(
        database_url=f"sqlite:///{db_path}",
        gc_retention_days=gc_retention_days,
    )

    # config.db_path 现在会正确地解析出我们传入的绝对路径
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()
    return coordinator


async def request_and_process(
    coordinator: Coordinator, tasks: list[dict], target_lang: str
):
    """辅助函数：异步地登记任务并处理它们。."""
    log.info(f"\n---> 开始登记 {len(tasks)} 个任务到 '{target_lang}' <---")
    for task in tasks:
        await coordinator.request(
            target_langs=[target_lang],
            text_content=task["text"],
            context=task.get("context"),
            business_id=task.get("business_id"),
        )
    log.info("所有任务登记完成。")

    log.info(f"\n---> 正在处理所有待翻译任务到 '{target_lang}' <---")
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]

    if results:
        for result in results:
            log.info("翻译结果", result=result)
    else:
        log.warning("没有需要处理的新任务（缓存命中）。")
    log.info("-" * 60)


async def main():
    """主程序入口：复杂异步工作流演示。."""
    setup_logging(log_level="INFO")
    load_dotenv()
    coordinator = await initialize_trans_hub(DB_FILE_PATH, GC_RETENTION_DAYS)

    try:
        zh = "zh-CN"
        fr = "fr"

        # --- 阶段 1: 首次翻译多种文本和上下文 ---
        log.info("=" * 20 + " 阶段 1: 首次翻译 " + "=" * 20)
        initial_tasks = [
            {"text": "Hello, world!", "business_id": "common.greeting.hello"},
            {
                "text": "Apple",
                "context": {"category": "fruit"},
                "business_id": "product.food.apple_fruit",
            },
            {
                "text": "Apple",
                "context": {"category": "company"},
                "business_id": "tech.company.apple_inc",
            },
            {
                "text": "Bank",
                "context": {"type": "financial_institution"},
                "business_id": "finance.building.bank_branch",
            },
            {
                "text": "Bank",
                "context": {"type": "geographical_feature"},
                "business_id": "geography.nature.river_bank",
            },
            {
                "text": "This is a very important system message.",
                "business_id": "system.message.important",
            },
            {
                "text": "Old feature text that will be cleaned up soon.",
                "business_id": "legacy.feature.old_text",
            },
        ]
        await request_and_process(coordinator, initial_tasks, zh)

        # --- 阶段 2: 演示缓存命中和 last_seen_at 更新 ---
        log.info("=" * 20 + " 阶段 2: 演示缓存命中 " + "=" * 20)
        cache_hit_tasks = [
            {"text": "Hello, world!", "business_id": "common.greeting.hello"},
            {
                "text": "Apple",
                "context": {"category": "fruit"},
                "business_id": "product.food.apple_fruit",
            },
        ]
        await request_and_process(coordinator, cache_hit_tasks, zh)

        # --- 阶段 3: 引入新的文本和新的语言 ---
        log.info("=" * 20 + " 阶段 3: 引入新任务 " + "=" * 20)
        new_tasks = [
            {
                "text": "Welcome to our new platform!",
                "business_id": "ui.onboarding.welcome_message",
            },
            {"text": "Translate me to French!", "business_id": "test.new.french_text"},
        ]
        await request_and_process(coordinator, new_tasks[:1], zh)
        await request_and_process(coordinator, new_tasks[1:], fr)

        # --- 阶段 4: 演示垃圾回收 (GC) ---
        log.info("=" * 20 + " 阶段 4: 演示垃圾回收 " + "=" * 20)
        log.info(f"配置的 GC 保留天数: {GC_RETENTION_DAYS} 天。")

        gc_report = await coordinator.run_garbage_collection(dry_run=True)
        log.info("GC 干跑报告", report=gc_report)
        log.info(f"预估将删除 {gc_report['deleted_sources']} 条源记录。")

        await coordinator.run_garbage_collection(dry_run=False)
        log.info("GC 已实际执行。")

    finally:
        if coordinator:
            log.info("正在关闭 Trans-Hub 协调器...")
            await coordinator.close()
            log.info("Trans-Hub 协调器已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
