# examples/07_real_world_simulation.py
"""
Trans-Hub v3.0 真实世界高并发模拟

本脚本将模拟一个多语言博客平台的后台系统，包含三个核心并发组件：
1.  内容生产者 (Producers): 多个并发的作者，向系统提交新文章。
2.  翻译工作进程 (Workers): 多个长期运行的后台任务，并发处理不同语言的翻译。
3.  API 服务 (API Server): 一个模拟的 API, 用于实时查询翻译结果。

它将全面展示 Trans-Hub 在高并发、多状态、长周期运行下的健壮性。

运行方式:
1. (可选) 如果想使用 OpenAI 引擎, 请在 .env 文件中配置 TH_OPENAI_API_KEY。
2. 在项目根目录执行: `poetry run python examples/07_real_world_simulation.py`
"""
import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Optional

import structlog

# --- 路径设置 ---
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(project_root))
# ---

from trans_hub import Coordinator, EngineName, TransHubConfig  # noqa: E402
from trans_hub.core import TranslationResult, TranslationStatus  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402

# --- 日志和环境配置 ---
setup_logging(log_level="INFO")
log = structlog.get_logger("trans_hub")
DB_FILE = Path(__file__).parent / "th_example_07.db"

# --- 模拟数据 ---
TARGET_LANGS = ["de", "fr"]
AUTHORS = ["Alice", "Bob", "Charlie"]
ARTICLES = [
    {"title": "The Future of AI", "content": "Artificial intelligence is evolving..."},
    {"title": "A Guide to Async Python", "content": "Asyncio provides tools..."},
    {"title": "Exploring the Cosmos", "content": "Space is the final frontier..."},
    {"title": "The Art of Cooking", "content": "Cooking is both a science and an art..."},
    {"title": "Sustainable Living", "content": "Living sustainably means..."},
]


async def content_producer(
    coordinator: Coordinator, author: str, shutdown_event: asyncio.Event
) -> None:
    """模拟一个内容生产者，定期发布新文章。"""
    article_index = 0
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=random.uniform(2, 5))
        except asyncio.TimeoutError:
            # It's time to publish
            article = random.choice(ARTICLES)
            business_id = f"article.{author.lower()}.{article_index}"
            source_payload = {
                "text": article["title"],
                "author": author,
                "body": article["content"],
            }
            log.info(f"✍️  [{author}] 正在发布新文章", business_id=business_id)
            await coordinator.request(
                business_id=business_id,
                source_payload=source_payload,
                target_langs=TARGET_LANGS,
            )
            article_index += 1


async def translation_worker(
    coordinator: Coordinator, lang: str, shutdown_event: asyncio.Event
) -> None:
    """模拟一个长期运行的、针对特定语言的翻译 Worker。"""
    log.info(f"👷 Worker for [{lang}] started.")
    while not shutdown_event.is_set():
        processed_count = 0
        async for result in coordinator.process_pending_translations(lang):
            processed_count += 1
            log.info(
                f"✅ [{lang}-Worker] 处理完成",
                business_id=result.business_id,
                status=result.status.value,
            )
        if processed_count == 0:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                continue


async def api_server(
    coordinator: Coordinator, shutdown_event: asyncio.Event
) -> None:
    """模拟一个 API 服务器，定期查询随机文章的翻译状态。"""
    log.info("📡 API Server started.")
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=1) # 每秒查询一次
        except asyncio.TimeoutError:
            random_author = random.choice(AUTHORS).lower()
            random_index = random.randint(0, 3)
            random_lang = random.choice(TARGET_LANGS)
            business_id_to_check = f"article.{random_author}.{random_index}"

            result: Optional[TranslationResult] = await coordinator.get_translation(
                business_id=business_id_to_check, target_lang=random_lang
            )
            status = result.status.value if result else "NOT_FOUND"
            log.info(
                f"API Query for [{business_id_to_check}][{random_lang}] -> {status}"
            )


async def main() -> None:
    """执行真实世界模拟。"""
    if DB_FILE.exists():
        DB_FILE.unlink()

    active_engine = (
        EngineName.OPENAI if "TH_OPENAI_API_KEY" in os.environ else EngineName.TRANSLATORS
    )
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE.resolve()}",
        source_lang="en",
        active_engine=active_engine,
    )
    apply_migrations(config.db_path)
    handler = create_persistence_handler(config)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    
    shutdown_event = asyncio.Event()

    try:
        await coordinator.initialize()
        log.info("✅ 协调器初始化成功", db_path=str(DB_FILE))

        log.warning("🚀 启动真实世界模拟... 运行约 15 秒后将自动停止。按 CTRL+C 可提前停止。")

        producer_tasks = [
            asyncio.create_task(content_producer(coordinator, author, shutdown_event))
            for author in AUTHORS
        ]
        worker_tasks = [
            asyncio.create_task(translation_worker(coordinator, lang, shutdown_event))
            for lang in TARGET_LANGS
        ]
        api_task = asyncio.create_task(api_server(coordinator, shutdown_event))

        all_tasks = producer_tasks + worker_tasks + [api_task]
        
        simulation_task = asyncio.gather(*all_tasks)
        
        # 让模拟运行一段时间
        await asyncio.sleep(15)

    except KeyboardInterrupt:
        log.warning("🛑 检测到 CTRL+C，正在准备优雅停机...")
    finally:
        log.warning("🏁 模拟时间到，正在准备优雅停机...")
        shutdown_event.set()
        # 等待所有任务响应关闭信号并完成
        if "simulation_task" in locals():
            await asyncio.sleep(1) # 给任务一点时间来响应事件
            simulation_task.cancel()
            await asyncio.gather(simulation_task, return_exceptions=True)
            
        await coordinator.close()
        log.info("🚪 系统已安全关闭。")
        if DB_FILE.exists():
            DB_FILE.unlink()


if __name__ == "__main__":
    asyncio.run(main())