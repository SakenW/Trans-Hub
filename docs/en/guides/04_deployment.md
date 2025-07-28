# main_app.py (应用入口)
from trans_hub.db.schema_manager import apply_migrations

# 在应用启动时
def startup():
    DB_FILE = "/path/to/your/production.db"

    print("正在检查并应用数据库迁移...")
    apply_migrations(DB_FILE)
    print("数据库已是最新版本。")

    # ... 后续的应用初始化逻辑 ...


# worker.py
import asyncio
import structlog
from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.logging_config import setup_logging

async def main():
    """一个长期运行的后台工作进程。"""
    setup_logging(log_level="INFO", log_format="json") # 生产环境使用 JSON 格式
    log = structlog.get_logger("worker")

    config = TransHubConfig()
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)

    try:
        await coordinator.initialize()
        log.info("后台 Worker 启动，开始监听待处理任务...")

        while True:
            try:
                target_languages = ["zh-CN", "fr", "de", "ja"]
                for lang in target_languages:
                    log.info(f"正在检查 '{lang}' 的任务...")
                    processed_count = 0
                    async for result in coordinator.process_pending_translations(lang):
                        processed_count += 1
                    if processed_count > 0:
                        log.info(f"本轮处理了 {processed_count} 个 '{lang}' 任务。")

                log.info("所有语言检查完毕，Worker 将在 60 秒后再次轮询。")
                await asyncio.sleep(60)

            except Exception:
                log.error("Worker 循环中发生意外错误，将在 60 秒后重试。", exc_info=True)
                await asyncio.sleep(60)
    finally:
        if "coordinator" in locals() and coordinator.initialized:
            await coordinator.close()
            log.info("后台 Worker 已关闭。")

if __name__ == "__main__":
    asyncio.run(main())


# a_batch_importer.py
import asyncio
from trans_hub import Coordinator

MAX_CONCURRENT_REQUESTS = 10 # 根据你的服务器性能和 I/O 调整

async def process_item(item: dict, coordinator: Coordinator, semaphore: asyncio.Semaphore):
    # 在执行操作前，先异步地获取信号量
    async with semaphore:
        # 这里的代码块，同时最多只会有 MAX_CONCURRENT_REQUESTS 个在运行
        await coordinator.request(
            target_langs=["zh-CN"],
            text_content=item["text"],
            business_id=item["id"]
        )

async def main():
    # ... (初始化 coordinator) ...
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    all_items = [...] # 假设这里有 1000 个项目

    tasks = [process_item(item, coordinator, semaphore) for item in all_items]
    await asyncio.gather(*tasks)

    # ...


30 3 * * * /path/to/your/poetry/bin/poetry run python /path/to/your/project/run_gc.py >> /var/log/trans-hub-gc.log 2>&1

