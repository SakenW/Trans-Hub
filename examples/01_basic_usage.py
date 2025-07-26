# examples/01_basic_usage.py
"""
Trans-Hub 的基础用法演示。

本脚本将向您展示 Trans-Hub 的核心工作流：
1.  初始化 Coordinator。
2.  登记一个翻译任务。
3.  执行待办任务并获取结果。
4.  再次尝试翻译，以演示持久化缓存的效果。

运行方式:
在项目根目录执行 `poetry run python examples/01_basic_usage.py`
"""

import asyncio
import sys
from pathlib import Path

import structlog

# -- 路径设置 --
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import (  # noqa: E402
    Coordinator,
    DefaultPersistenceHandler,
    TransHubConfig,
)
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402


async def get_or_create_coordinator(db_name: str = "basic_usage_demo.db"):
    """一个健壮的异步工厂函数，用于获取一个初始化完成的 Coordinator 实例。"""
    log = structlog.get_logger("initializer")
    db_path = Path(__file__).parent / db_name

    if not db_path.exists():
        log.info("数据库不存在，正在创建并迁移...", db_path=str(db_path))
        apply_migrations(str(db_path))

    config = TransHubConfig(database_url=f"sqlite:///{db_path.resolve()}")
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)

    await coordinator.initialize()
    return coordinator


async def main():
    """程序的主异步入口。"""
    setup_logging(log_level="INFO")
    log = structlog.get_logger("main")

    coordinator = None
    db_path = Path(__file__).parent / "basic_usage_demo.db"
    db_path.unlink(missing_ok=True)

    try:
        coordinator = await get_or_create_coordinator()

        text_to_translate = "The journey of a thousand miles begins with a single step."
        target_lang = "zh-CN"
        text_id = "quotes.laozi.journey"

        log.info("▶️ 第一次尝试翻译...")
        log.info("登记翻译任务", text=text_to_translate, business_id=text_id)
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id,
        )
        log.info(f"处理 '{target_lang}' 的待翻译任务...")
        processed_results = [
            res
            async for res in coordinator.process_pending_translations(
                target_lang=target_lang
            )
        ]
        if processed_results:
            log.info("翻译完成！", result=processed_results[0].translated_content)
        else:
            log.warning("没有需要处理的新任务。")

        log.info("\n▶️ 第二次尝试翻译 (模拟缓存命中)...")
        log.info("再次登记同一个翻译任务", text=text_to_translate, business_id=text_id)
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id,
        )
        log.info(f"再次处理 '{target_lang}' 的待翻译任务...")
        processed_again = [
            res
            async for res in coordinator.process_pending_translations(
                target_lang=target_lang
            )
        ]
        if not processed_again:
            log.info("✅ 成功！没有需要处理的新任务，表明持久化缓存生效。")
            existing_translation = await coordinator.get_translation(
                text_content=text_to_translate, target_lang=target_lang
            )
            if existing_translation and existing_translation.translated_content:
                log.info(
                    "直接从缓存/数据库获取到已有的翻译",
                    result=existing_translation.translated_content,
                )

    except Exception as e:
        log.error("程序发生意外错误", error=str(e), exc_info=True)
    finally:
        if coordinator:
            await coordinator.close()
            log.info("数据库连接已关闭。")
        db_path.unlink(missing_ok=True)
        log.info("临时数据库已删除。")


if __name__ == "__main__":
    asyncio.run(main())
