# examples/02_real_world_simulation.py
"""
一个复杂的、偏重现实环境的 Trans-Hub 端到端模拟。

本脚本将模拟一个多语言博客平台的后台系统，包含三个核心并发组件：
1.  内容生产者 (Producers): 多个并发的作者，向系统提交新文章。
2.  翻译工作进程 (Worker): 一个长期运行的后台任务，处理所有语言的翻译。
3.  API 服务 (API Server): 一个模拟的 API, 用于实时查询翻译结果。

它将全面展示 Trans-Hub 在高并发、多状态、长周期运行下的健壮性和高级功能。

运行方式:
1. 确保在 .env 文件中配置了 TH_OPENAI_API_KEY 和 TH_OPENAI_MODEL (推荐 gpt-4o)。
2. 在项目根目录执行 `poetry run python examples/02_real_world_simulation.py`
"""

import asyncio
import random
import sys
from pathlib import Path
from typing import Optional

import structlog
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trans_hub import Coordinator, TransHubConfig, TranslationStatus  # noqa: E402
from trans_hub.config import EngineName  # noqa: E402
from trans_hub.db.schema_manager import apply_migrations  # noqa: E402
from trans_hub.exceptions import ConfigurationError  # noqa: E402
from trans_hub.logging_config import setup_logging  # noqa: E402
from trans_hub.persistence import create_persistence_handler  # noqa: E402
from trans_hub.types import TranslationResult  # noqa: E402

DB_FILE_PATH = PROJECT_ROOT / "examples/02_real_world_simulation.db"
TARGET_LANGS = ["zh-CN", "fr", "es"]
NUM_PRODUCERS = 3
SIMULATION_DURATION = 20

log = structlog.get_logger("simulation")


def get_article_context(category: str) -> dict:
    """为特定类别的文章生成上下文。"""
    return {
        "source": "demo_workflow",
        "category": category,
        "system_prompt": f"You are a professional translator specializing in '{category}'. Translate for a blog. Provide only the translated text, without quotes.",
    }


async def initialize_trans_hub() -> Optional[Coordinator]:
    """标准的异步初始化函数，如果配置无效则返回 None。"""
    DB_FILE_PATH.unlink(missing_ok=True)
    apply_migrations(str(DB_FILE_PATH.resolve()))

    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE_PATH.resolve()}",
        active_engine=EngineName("openai"),
        source_lang="en",
    )

    try:
        handler = create_persistence_handler(config)
        coordinator = Coordinator(config=config, persistence_handler=handler)
        # Initialize 会执行引擎的健康检查
        await coordinator.initialize()
        log.info("✅ Trans-Hub 初始化成功！")
        return coordinator
    except ConfigurationError as e:
        log.error(
            "❌ Trans-Hub 初始化失败！很可能是 OpenAI 配置错误。",
            error=str(e),
            suggestion="请检查您的 .env 文件中是否正确配置了 TH_OPENAI_API_KEY, TH_OPENAI_ENDPOINT 和 TH_OPENAI_MODEL。",
        )
        return None
    except Exception:
        log.error("❌ Trans-Hub 初始化时发生未知严重错误。", exc_info=True)
        return None


async def content_producer(
    coordinator: Coordinator, producer_id: int, stop_event: asyncio.Event
):
    """模拟一个内容生产者（作者），随机提交新内容。"""
    plog = log.bind(component="Producer", producer_id=producer_id)
    plog.info("启动！")
    articles = [
        {
            "title": "The Future of AI",
            "content": "Artificial intelligence is evolving at an unprecedented pace.",
            "category": "technology",
        },
        {
            "title": "A Walk in the Park",
            "content": "The leaves crunched under my feet, a symphony of autumn.",
            "category": "prose",
        },
        {
            "title": "Server Migration Guide",
            "content": "Migrating a live server requires careful planning.",
            "category": "technology",
        },
        {
            "title": "The Last Star",
            "content": "In the vast darkness, a single star blinked.",
            "category": "fiction",
        },
    ]
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=random.uniform(1, 3))
        except asyncio.TimeoutError:
            pass
        else:
            break

        article = random.choice(articles)
        business_id_base = (
            f"article_{article['title'].replace(' ', '_').lower()}_{producer_id}"
        )
        context = get_article_context(article["category"])

        plog.info("提交新文章", title=article["title"])
        await coordinator.request(
            target_langs=TARGET_LANGS,
            text_content=article["title"],
            business_id=f"{business_id_base}_title",
            context=context,
        )
        await coordinator.request(
            target_langs=TARGET_LANGS,
            text_content=article["content"],
            business_id=f"{business_id_base}_content",
            context=context,
        )
    plog.info("停止。")


async def translation_worker(coordinator: Coordinator, stop_event: asyncio.Event):
    """模拟一个后台翻译工作进程。"""
    wlog = log.bind(component="Worker")
    wlog.info("启动！开始轮询待办任务...")
    while not stop_event.is_set():
        processed_in_cycle = 0
        for lang in TARGET_LANGS:
            try:
                # 每次处理最多10个任务，避免长时间阻塞
                async for result in coordinator.process_pending_translations(
                    lang, limit=10
                ):
                    if (
                        result.status == TranslationStatus.TRANSLATED
                        and result.translated_content
                    ):
                        wlog.info(
                            f"✅ 翻译成功 -> {lang}",
                            original=f"'{result.original_content[:20]}...'",
                            translated=f"'{result.translated_content[:20]}...'",
                        )
                    processed_in_cycle += 1
            except Exception:
                wlog.error("处理批次时出错", exc_info=True)

        if processed_in_cycle == 0:
            wlog.debug("本轮无新任务，休眠...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
    wlog.info("停止。")


async def api_server(coordinator: Coordinator, stop_event: asyncio.Event):
    """模拟一个 API 服务，随机查询翻译结果。"""
    alog = log.bind(component="API")
    alog.info("启动！开始接收模拟查询...")
    articles = [
        {"title": "The Future of AI", "category": "technology"},
        {"title": "A Walk in the Park", "category": "prose"},
        {"title": "Non-existent text", "category": "fiction"},
    ]
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=random.uniform(2, 4))
        except asyncio.TimeoutError:
            pass
        else:
            break

        query_article = random.choice(articles)
        query_text = query_article["title"]
        target_lang = random.choice(TARGET_LANGS)

        alog.info("收到查询", text=f"'{query_text}'", lang=target_lang)
        result: Optional[TranslationResult] = await coordinator.get_translation(
            text_content=query_text,
            target_lang=target_lang,
            context=get_article_context(query_article["category"]),
        )
        if result:
            alog.info("✅ 查询命中", result=f"'{result.translated_content}'")
        else:
            alog.warning("🟡 查询未命中或尚未翻译", text=f"'{query_text}'")
    alog.info("停止。")


async def main():
    """主程序入口，协调所有组件的生命周期。"""
    setup_logging(log_level="INFO")
    load_dotenv()
    coordinator = None
    tasks = []
    try:
        coordinator = await initialize_trans_hub()
        if not coordinator:
            log.error("由于初始化失败，模拟程序无法启动。")
            return

        stop_event = asyncio.Event()
        log.info("🚀 启动模拟系统...", duration=f"{SIMULATION_DURATION}s")
        producer_tasks = [
            asyncio.create_task(content_producer(coordinator, i, stop_event))
            for i in range(1, NUM_PRODUCERS + 1)
        ]
        worker_task = asyncio.create_task(translation_worker(coordinator, stop_event))
        api_task = asyncio.create_task(api_server(coordinator, stop_event))
        tasks = producer_tasks + [worker_task, api_task]

        await asyncio.sleep(SIMULATION_DURATION)

    except Exception:
        log.error("模拟主循环发生意外错误", exc_info=True)
    finally:
        log.info("🔴 停止模拟系统...")
        if "stop_event" in locals():
            stop_event.set()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if coordinator:
            await coordinator.close()
        log.info("✅ 模拟结束。")
        relative_db_path = DB_FILE_PATH.relative_to(PROJECT_ROOT)
        print(
            f"\n数据库已保留，请使用以下命令检查内容：\npoetry run python tools/inspect_db.py {relative_db_path}\n"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n用户手动中断。")
