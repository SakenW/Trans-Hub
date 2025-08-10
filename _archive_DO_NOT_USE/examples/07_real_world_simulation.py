# examples/07_real_world_simulation.py
"""
Trans-Hub v3.0 真实世界高并发模拟 (重构版)
"""
import asyncio
import os
import random
from examples._shared import example_runner, log
from trans_hub import Coordinator, EngineName

# --- 模拟数据 ---
TARGET_LANGS = ["de", "fr"]
AUTHORS = ["Alice", "Bob"]
ARTICLES = [
    {"title": "The Future of AI", "content": "AI is evolving..."},
    {"title": "A Guide to Async Python", "content": "Asyncio provides tools..."},
    {"title": "Exploring the Cosmos", "content": "Space is the final frontier..."},
]

async def content_producer(coord: Coordinator, author: str, event: asyncio.Event):
    """模拟内容生产者。"""
    idx = 0
    while not event.is_set():
        try:
            await asyncio.wait_for(event.wait(), timeout=random.uniform(2, 4))
        except TimeoutError:
            article = random.choice(ARTICLES)
            b_id = f"article.{author.lower()}.{idx}"
            payload = {"text": article["title"], "body": article["content"]}
            log.info(f"✍️  [{author}] 发布新文章", business_id=b_id)
            await coord.request(business_id=b_id, source_payload=payload, target_langs=TARGET_LANGS)
            idx += 1

async def translation_worker(coord: Coordinator, lang: str, event: asyncio.Event):
    """模拟翻译 Worker。"""
    log.info(f"👷 Worker for [{lang}] started.")
    while not event.is_set():
        processed = 0
        async for result in coord.process_pending_translations(lang):
            processed += 1
            log.info(f"✅ [{lang}-Worker] 处理完成", b_id=result.business_id, status=result.status.value)
        if processed == 0:
            try:
                await asyncio.wait_for(event.wait(), timeout=2)
            except TimeoutError:
                continue

async def api_server(coord: Coordinator, event: asyncio.Event):
    """模拟 API 服务器。"""
    log.info("📡 API Server started.")
    while not event.is_set():
        try:
            await asyncio.wait_for(event.wait(), timeout=1)
        except TimeoutError:
            b_id = f"article.{random.choice(AUTHORS).lower()}.{random.randint(0, 3)}"
            lang = random.choice(TARGET_LANGS)
            result = await coord.get_translation(business_id=b_id, target_lang=lang)
            status = result.status.value if result else "NOT_FOUND"
            log.info(f"API Query for [{b_id}][{lang}] -> {status}")

async def main() -> None:
    """执行真实世界模拟。"""
    engine = EngineName.OPENAI if "TH_OPENAI_API_KEY" in os.environ else EngineName.TRANSLATORS
    shutdown_event = asyncio.Event()

    async with example_runner("th_example_07.db", active_engine=engine) as coordinator:
        log.warning("🚀 启动真实世界模拟... 运行约 15 秒后将自动停止。")
        
        components = [
            *(content_producer(coordinator, author, shutdown_event) for author in AUTHORS),
            *(translation_worker(coordinator, lang, shutdown_event) for lang in TARGET_LANGS),
            api_server(coordinator, shutdown_event),
        ]
        
        simulation_task = asyncio.gather(*components)
        try:
            await asyncio.wait_for(simulation_task, timeout=15)
        except TimeoutError:
            log.warning("🏁 模拟时间到，准备优雅停机...")
        except KeyboardInterrupt:
            log.warning("🛑 检测到 CTRL+C，准备优雅停机...")
        finally:
            shutdown_event.set()
            # 给任务一点时间响应事件并取消
            await asyncio.sleep(1)
            simulation_task.cancel()
            await asyncio.gather(simulation_task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())