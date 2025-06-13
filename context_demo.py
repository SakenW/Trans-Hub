# main.py (最终最终修正版)
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

# 导入 Trans-Hub 的核心组件
from dotenv import load_dotenv

from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationStatus  # 从 types 导入 TranslationStatus

# 获取一个 logger
log = structlog.get_logger()

# 统一的数据库文件路径
DB_FILE = "my_complex_trans_hub_demo.db"
# 为了演示 GC，我们将保留天数设置为 0。
GC_RETENTION_DAYS_FOR_DEMO = 0


def initialize_trans_hub(db_file: str, gc_retention_days: int) -> Coordinator:
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    setup_logging(log_level="INFO")  # 保持 INFO 级别，除非需要详细调试
    # setup_logging(log_level="DEBUG") # 如果需要详细调试，请解除注释

    # 每次运行前，删除旧数据库文件，确保一个干净的演示环境
    if os.path.exists(db_file):
        os.remove(db_file)
        log.info(f"已删除旧数据库文件: {db_file}", db_path=db_file)

    log.info("数据库文件不存在，正在创建并应用迁移。", db_path=db_file)
    apply_migrations(db_file)

    handler = DefaultPersistenceHandler(db_path=db_file)

    config = TransHubConfig(
        database_url=f"sqlite:///{db_file}",
        engine_configs=EngineConfigs(),
        gc_retention_days=gc_retention_days,  # 传入 GC 保留天数
    )

    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator


def request_and_process(
    coordinator: Coordinator, tasks: List[Dict[str, Any]], target_lang: str
):
    """辅助函数：登记任务并处理它们。"""
    log.info(f"\n---> 开始登记 {len(tasks)} 个任务到 {target_lang} <---")
    for i, task in enumerate(tasks):
        log.info(
            f"正在登记任务 {i+1}/{len(tasks)}: '{task['purpose']}'",
            text=task["text"],
            context=task["context"],
            lang=target_lang,
            business_id=task.get("business_id"),
        )
        coordinator.request(
            target_langs=[target_lang],
            text_content=task["text"],
            context=task["context"],
            business_id=task.get("business_id"),  # business_id 可能是 None
        )

    log.info(f"\n---> 正在处理所有待翻译任务到 '{target_lang}' <---")
    results_generator = coordinator.process_pending_translations(
        target_lang=target_lang
    )

    results = list(results_generator)

    if results:
        log.info(f"成功处理 {len(results)} 个任务。")
        for result in results:
            source_info = "从缓存获取" if result.from_cache else "新翻译"
            log.info(
                "翻译结果：",
                original=result.original_content,
                context=result.context_hash,  # context_hash 现在总是字符串
                translation=result.translated_content,
                status=result.status.name,
                engine=result.engine,
                business_id=result.business_id
                if result.business_id
                else "无 business_id",  # 正确显示 business_id
                source=source_info,
            )
    else:
        log.warning("没有需要处理的新任务。")
    log.info("\n" + "=" * 60 + "\n")


def main():
    """主程序入口：复杂任务测试。"""
    load_dotenv()
    coordinator = None
    try:
        coordinator = initialize_trans_hub(DB_FILE, GC_RETENTION_DAYS_FOR_DEMO)
        target_language_code_zh = "zh-CN"
        target_language_code_fr = "fr"

        # --- 阶段 1: 首次翻译多种文本和上下文 ---
        log.info("=== 阶段 1: 首次翻译多种文本和上下文 ===")
        initial_tasks = [
            {
                "text": "Hello, world!",
                "context": None,
                "business_id": "common.greeting.hello",
                "purpose": "基础问候语",
            },
            {
                "text": "Apple",
                "context": {"category": "fruit"},
                "business_id": "product.food.apple_fruit",
                "purpose": "苹果（水果）",
            },
            {
                "text": "Apple",
                "context": {"category": "company"},
                "business_id": "tech.company.apple_inc",
                "purpose": "苹果（公司）",
            },
            {
                "text": "Bank",
                "context": {"type": "financial_institution"},
                "business_id": "finance.building.bank_branch",
                "purpose": "银行（金融）",
            },
            {
                "text": "Bank",
                "context": {"type": "geographical_feature"},
                "business_id": "geography.nature.river_bank",
                "purpose": "河岸（地理）",
            },
            {
                "text": "This is a very important system message.",
                "context": None,
                "business_id": "system.message.important",
                "purpose": "重要系统消息 (到中文)",
            },
            {
                "text": "This is a very important system message.",
                "context": None,
                "business_id": "system.message.important_fr",
                "purpose": "重要系统消息 (到法语)",
            },
            {
                "text": "Old feature text that will be cleaned up soon.",
                "context": None,
                "business_id": "legacy.feature.old_text",
                "purpose": "即将被 GC 的旧功能文本",
            },
        ]

        request_and_process(coordinator, initial_tasks[:6], target_language_code_zh)
        request_and_process(coordinator, initial_tasks[6:7], target_language_code_fr)
        request_and_process(coordinator, initial_tasks[7:8], target_language_code_zh)

        # --- 阶段 2: 演示缓存命中和 last_seen_at 更新 ---
        log.info("=== 阶段 2: 演示缓存命中和 last_seen_at 更新 ===")
        cache_hit_tasks = [
            {
                "text": "Hello, world!",
                "context": None,
                "business_id": "common.greeting.hello",
                "purpose": "再次请求基础问候语 (期望缓存)",
            },
            {
                "text": "Apple",
                "context": {"category": "fruit"},
                "business_id": "product.food.apple_fruit",
                "purpose": "再次请求苹果（水果）(期望缓存)",
            },
            {
                "text": "This is a very important system message.",
                "context": None,
                "business_id": "system.message.important_fr",
                "purpose": "再次请求重要系统消息 (法语 - 期望缓存)",
            },
        ]
        request_and_process(coordinator, cache_hit_tasks[:2], target_language_code_zh)
        request_and_process(coordinator, cache_hit_tasks[2:], target_language_code_fr)

        # --- 阶段 3: 引入新的文本，看它如何被处理 ---
        log.info("=== 阶段 3: 引入新的文本，看它如何被处理 ===")
        new_tasks = [
            {
                "text": "Welcome to our new platform!",
                "context": None,
                "business_id": "ui.onboarding.welcome_message",
                "purpose": "新用户欢迎语 (新翻译)",
            },
            {
                "text": "Login successful.",
                "context": None,
                "business_id": "ui.auth.login_success",
                "purpose": "登录成功消息 (新翻译)",
            },
            {
                "text": "Translate me in French!",
                "context": None,
                "business_id": "test.new.french_text",
                "purpose": "新的法语翻译任务",
            },
        ]
        request_and_process(coordinator, new_tasks[:2], target_language_code_zh)
        request_and_process(coordinator, new_tasks[2:], target_language_code_fr)

        # --- 阶段 4: 演示垃圾回收 (GC) ---
        log.info("=== 阶段 4: 演示垃圾回收 (GC) 功能 ===")
        log.info(f"配置的 GC 保留天数: {GC_RETENTION_DAYS_FOR_DEMO} 天。")
        log.info("第一次运行 GC (干跑模式: dry_run=True)...")

        gc_report_dry_run = coordinator.run_garbage_collection(
            retention_days=GC_RETENTION_DAYS_FOR_DEMO, dry_run=True
        )
        log.info("GC 干跑报告：", report=gc_report_dry_run)
        if gc_report_dry_run["deleted_sources"] > 0:
            log.info(f"预估将删除 {gc_report_dry_run['deleted_sources']} 条源记录。")
            log.info(f"其中应该包含 'legacy.feature.old_text'。")
        else:
            log.info("没有源记录被报告为可删除。这可能意味着所有业务ID的last_seen_at都是最新。")

        log.info("\n" + "-" * 50 + "\n")
        log.info("第二次运行 GC (实际删除模式: dry_run=False)...")

        gc_report_actual = coordinator.run_garbage_collection(
            retention_days=GC_RETENTION_DAYS_FOR_DEMO, dry_run=False
        )
        log.info("GC 实际执行报告：", report=gc_report_actual)
        if gc_report_actual["deleted_sources"] > 0:
            log.info(f"实际已删除 {gc_report_actual['deleted_sources']} 条源记录。")
            log.info("请检查数据库文件，'legacy.feature.old_text' 相关的 th_sources 记录应该已被删除。")
        else:
            log.info("没有源记录被删除。")

        log.info("\n" + "=" * 60 + "\n")

        # --- 阶段 5: 验证 GC 后，再次请求被清理的 business_id ---
        log.info("=== 阶段 5: 验证 GC 后，再次请求被清理的 business_id ===")
        re_requested_task = [
            {
                "text": "Old feature text that will be cleaned up soon.",
                "context": None,
                "business_id": "legacy.feature.old_text",
                "purpose": "再次请求已被 GC 的旧功能文本 (应重新添加 source 记录并从 cache 获取翻译)",
            },
        ]
        log.info(f"尝试再次登记业务ID：'{re_requested_task[0]['business_id']}'...")
        coordinator.request(
            target_langs=[target_language_code_zh],
            text_content=re_requested_task[0]["text"],
            context=re_requested_task[0]["context"],
            business_id=re_requested_task[0]["business_id"],
        )

        log.info("处理再次请求的旧功能文本任务...")
        results_generator_re_requested = coordinator.process_pending_translations(
            target_lang=target_language_code_zh
        )
        re_requested_results = list(results_generator_re_requested)

        if re_requested_results:
            result = re_requested_results[0]
            log.info(
                "重新请求 GC 业务ID的结果：",
                original=result.original_content,
                translation=result.translated_content,
                status=result.status.name,
                engine=result.engine,
                business_id=result.business_id
                if result.business_id
                else "无 business_id",
                source="从缓存获取" if result.from_cache else "新翻译 (应不发生)",
            )
            log.info(
                f"注意：'business_id' '{result.business_id}' 在 th_sources 中的 last_seen_at 已被更新。"
            )
        else:
            log.warning("重新请求的任务没有结果。")

    except Exception as e:
        log.critical("程序运行中发生未知严重错误！", exc_info=True)
    finally:
        if coordinator:
            log.info("正在关闭 Trans-Hub 协调器...")
            coordinator.close()
            log.info("Trans-Hub 协调器已关闭。")


if __name__ == "__main__":
    main()
