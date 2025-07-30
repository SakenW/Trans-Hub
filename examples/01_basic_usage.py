# examples/01_basic_usage.py
"""Trans-Hub 的基础用法演示。"""

# --- 最终修复：将 sys.path hack 放在顶部，并为后续导入添加 noqa: E402 ---
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 1. 标准库导入
import asyncio  # noqa: E402

# 2. 第三方库导入
import structlog  # noqa: E402

# 3. 本项目库导入
from trans_hub import (  # noqa: E402
    Coordinator,
    EngineName,
    TransHubConfig,
    create_persistence_handler,
)
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402

log = structlog.get_logger("basic_usage")


async def get_coordinator(db_name: str = "01_basic_usage_demo.db") -> Coordinator:
    db_path_obj = Path(__file__).parent / db_name
    db_path_str = str(db_path_obj.resolve())
    db_path_obj.unlink(missing_ok=True)
    log.info("旧数据库已清理。", path=db_path_str)
    log.info("正在应用数据库迁移...")
    apply_migrations(db_path_str)
    log.info("数据库迁移完成。")
    config = TransHubConfig(
        database_url=f"sqlite:///{db_path_str}", active_engine=EngineName.DEBUG
    )
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()
    return coordinator


async def main() -> None:
    setup_logging(log_level="INFO", log_format="console")
    coordinator = None
    try:
        coordinator = await get_coordinator()
        text_to_translate = "The journey of a thousand miles begins with a single step."
        target_lang = "zh-CN"
        text_id = "quotes.laozi.journey"
        log.info("▶️ 步骤 1: 异步提交翻译任务到队列...")
        await coordinator.request(
            target_langs=[target_lang],
            text_content=text_to_translate,
            business_id=text_id,
        )
        log.info("✅ 任务已入队。", text=text_to_translate)
        log.info("▶️ 步骤 2: 在后台启动一个工作进程处理任务...")
        worker_task = asyncio.create_task(
            coordinator.process_pending_translations(target_lang).__anext__()
        )
        log.info("▶️ 步骤 3: 在前台轮询，直到获取到翻译结果...")
        translation = None
        for i in range(10):
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
        await worker_task
        log.info("\n▶️ 步骤 4: 再次获取翻译，演示持久化效果...")
        cached_translation = await coordinator.get_translation(
            text_content=text_to_translate, target_lang=target_lang
        )
        if cached_translation:
            log.info(
                "✅ 再次调用 get_translation 立即成功！",
                result=cached_translation.translated_content,
                source="数据库/内存缓存",
            )
    except Exception:
        log.error("程序发生意外错误", exc_info=True)
    finally:
        if coordinator:
            await coordinator.close()
            log.info("所有资源已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
