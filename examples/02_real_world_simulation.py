# examples/02_real_world_simulation.py
"""
一个超级复杂的、偏重现实环境的 Trans-Hub 端到端模拟。

本脚本将模拟一个多语言博客平台的后台系统，包含三个核心并发组件：
1.  **内容生产者 (Producers)**: 多个并发的作者，向系统提交新文章。
2.  **翻译工作进程 (Worker)**: 一个长期运行的后台任务，处理所有语言的翻译。
3.  **API 服务 (API Server)**: 一个模拟的 API, 用于实时查询翻译结果。

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
from trans_hub.types import TranslationResult  # noqa: E402

# --- 演示配置 ---
DB_FILE_PATH = PROJECT_ROOT / "02_real_world_simulation.db"
TARGET_LANGS = ["zh-CN", "fr", "es"]
NUM_PRODUCERS = 3
SIMULATION_DURATION = 15

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
            break
        except asyncio.TimeoutError:
            pass
        article = random.choice(articles)
        business_id = (
            f"article_{article['title'].replace(' ', '_').lower()}_{producer_id}"
        )
        plog.info("提交新文章", title=article["title"], biz_id=business_id)
        context = {
            "source": f"producer-{producer_id}",
            "category": article["category"],
            "system_prompt": f"You are translating content for a blog about '{article['category']}'.",
        }
        await coordinator.request(
            target_langs=TARGET_LANGS,
            text_content=article["title"],
            business_id=f"{business_id}_title",
            context=context,
        )
        await coordinator.request(
            target_langs=TARGET_LANGS,
            text_content=article["content"],
            business_id=f"{business_id}_content",
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
                async for result in coordinator.process_pending_translations(
                    lang, limit=10
                ):
                    if (
                        result.status == TranslationStatus.TRANSLATED
                        and result.translated_content
                    ):
                        wlog.info(
                            f"✅ 翻译成功 -> {lang}",
                            original=result.original_content[:20] + "...",
                            translated=result.translated_content[:20] + "...",
                        )
                    processed_in_cycle += 1
            except Exception:
                wlog.error("处理批次时出错", exc_info=True)
        if processed_in_cycle == 0:
            wlog.info("本轮无新任务，休眠5秒...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
    wlog.info("停止。")


async def api_server(coordinator: Coordinator, stop_event: asyncio.Event):
    """模拟一个 API 服务，随机查询翻译结果。"""
    alog = log.bind(component="API")
    alog.info("启动！开始接收模拟查询...")
    queries = ["The Future of AI", "A Walk in the Park", "Non-existent text"]
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=random.uniform(2, 4))
            break
        except asyncio.TimeoutError:
            pass
        query_text = random.choice(queries)
        target_lang = random.choice(TARGET_LANGS)
        alog.info("收到查询", text=query_text, lang=target_lang)
        result: Optional[TranslationResult] = await coordinator.get_translation(
            text_content=query_text,
            target_lang=target_lang,
            context=generate_context_for_text(
                query_text, "technology" if "AI" in query_text else "prose"
            ),
        )
        if result:
            alog.info("✅ 查询命中", result=result.translated_content)
        else:
            alog.warning("🟡 查询未命中或尚未翻译", text=query_text)
    alog.info("停止。")


async def main():
    """主程序入口，协调所有组件的生命周期。"""
    setup_logging(log_level="INFO")
    load_dotenv()
    coordinator = None
    tasks = []
    try:
        coordinator = await initialize_trans_hub()
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
        log.info("临时数据库已保留，请使用以下命令检查内容：")
        relative_db_path = DB_FILE_PATH.relative_to(PROJECT_ROOT)
        print(f"\npoetry run python tools/inspect_db.py {relative_db_path}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("用户手动中断。")
