# examples/01_basic_usage.py
"""
Trans-Hub 的基础用法演示。

本脚本将向您展示 Trans-Hub 的核心工作流：
1.  初始化 Coordinator (使用新的工厂模式)。
2.  异步地请求一个翻译任务，并将其加入队列。
3.  启动一个后台工作进程来处理队列中的任务。
4.  在前台立即尝试获取翻译结果，演示如何轮询或等待翻译完成。

运行方式:
在项目根目录执行 `poetry run python examples/01_basic_usage.py`
"""

import asyncio
import sys
from pathlib import Path

import structlog

# -- 路径设置，确保能从 examples 目录找到 trans_hub 包 --
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import Coordinator, TransHubConfig  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

# --- 核心修正：使用新的工厂模式和接口 ---
from trans_hub.persistence import create_persistence_handler  # noqa: E402

log = structlog.get_logger("basic_usage")


async def get_coordinator(db_name: str = "01_basic_usage_demo.db") -> Coordinator:
    """一个标准的异步工厂函数，用于获取一个初始化完成的 Coordinator 实例。"""
    db_path_obj = Path(__file__).parent / db_name
    db_path_str = str(db_path_obj.resolve())

    # 确保每次运行时都是一个全新的数据库
    db_path_obj.unlink(missing_ok=True)
    log.info("旧数据库已清理。", path=db_path_str)

    log.info("正在应用数据库迁移...")
    apply_migrations(db_path_str)
    log.info("数据库迁移完成。")

    config = TransHubConfig(database_url=f"sqlite:///{db_path_str}")
    # --- 核心修正：使用工厂函数创建 handler ---
    handler = create_persistence_handler(config)

    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()
    return coordinator


async def main() -> None:
    """程序的主异步入口。"""
    setup_logging(log_level="INFO")
    coordinator = None
    try:
        coordinator = await get_coordinator()

        text_to_translate = "The journey of a thousand miles begins with a single step."
        target_lang = "zh-CN"
        text_id = "quotes.laozi.journey"

        # --- 流程 1: 异步请求与处理 ---
        log.info("▶️ 步骤 1: 异步提交翻译任务到队列...")
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id,
        )
        log.info("✅ 任务已入队。", text=text_to_translate)

        log.info("▶️ 步骤 2: 在后台启动一个工作进程处理任务...")
        # 在真实应用中，这会是一个独立的、长期运行的进程或任务
        # 这里我们使用 __anext__ 来只处理一个批次
        worker_task = asyncio.create_task(
            coordinator.process_pending_translations(target_lang).__anext__()
        )

        # --- 流程 2: 前台轮询获取结果 ---
        log.info("▶️ 步骤 3: 在前台轮询，直到获取到翻译结果...")
        translation = None
        for i in range(10):  # 最多尝试10次，每次间隔0.5秒
            await asyncio.sleep(0.5)
            log.info(f"第 {i + 1} 次尝试获取翻译...")
            translation = await coordinator.get_translation(
                text_content=text_to_translate, target_lang=target_lang
            )
            if translation:
                log.info("✅ 成功获取到翻译！", result=translation.translated_content)
                break
        else:
            log.error("❌ 在超时时间内未能获取到翻译结果。")

        # 确保后台任务完成
        await worker_task

        log.info("\n▶️ 步骤 4: 再次获取翻译，演示持久化效果...")
        # 此时因为内存缓存和数据库都已有数据，调用会立即返回
        cached_translation = await coordinator.get_translation(
            text_content=text_to_translate, target_lang=target_lang
        )
        if cached_translation:
            log.info(
                "✅ 再次调用 get_translation 立即成功！",
                result=cached_translation.translated_content,
                source="数据库/内存缓存",
            )

    except Exception as e:
        log.error("程序发生意外错误", error=str(e), exc_info=True)
    finally:
        if coordinator:
            await coordinator.close()
            log.info("所有资源已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
