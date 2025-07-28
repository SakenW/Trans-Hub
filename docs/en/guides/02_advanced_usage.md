pip install "trans-hub[openai]"


# .env
TH_OPENAI_ENDPOINT="https://api.openai.com/v1"
TH_OPENAI_API_KEY="your-secret-openai-key"
TH_OPENAI_MODEL="gpt-4o"


# a_script_with_openai.py
from trans_hub.config import TransHubConfig
# ... 其他导入与初始化代码 ...

config = TransHubConfig(active_engine="openai", source_lang="en")
coordinator = Coordinator(config=config, persistence_handler=handler)
# ...


import asyncio
import os
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

# 确保 trans_hub 在路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging

# --- 准备工作 ---
load_dotenv()
setup_logging()
log = structlog.get_logger()
DB_FILE = "context_demo.db"


async def main():
    # --- 1. 初始化 ---
    if os.path.exists(DB_FILE): os.remove(DB_FILE)
    apply_migrations(DB_FILE)
    
    config = TransHubConfig(
        database_url=f"sqlite:///{Path(DB_FILE).resolve()}",
        active_engine="openai",
        source_lang="en"
    )
    handler = DefaultPersistenceHandler(config.db_path)
    coordinator = Coordinator(config, handler)
    await coordinator.initialize()
    
    try:
        target_lang = "zh-CN"
        tasks = [
            {
                "text": "Jaguar",
                "context": {"system_prompt": "You are a professional translator specializing in wildlife and animals."},
                "business_id": "wildlife.big_cat.jaguar",
            },
            {
                "text": "Jaguar",
                "context": {"system_prompt": "You are a professional translator specializing in luxury car brands."},
                "business_id": "automotive.brand.jaguar",
            },
        ]

        # --- 2. 登记任务 ---
        for task in tasks:
            await coordinator.request(
                target_langs=[target_lang], text_content=task['text'],
                context=task['context'], business_id=task['business_id']
            )

        # --- 3. 处理并打印结果 ---
        log.info("正在处理 'Jaguar' 的两个不同上下文的翻译...")
        results = [res async for res in coordinator.process_pending_translations(target_lang)]
        for result in results:
            log.info("✅ 翻译结果", 
                     original=result.original_content, 
                     translated=result.translated_content, 
                     biz_id=result.business_id)

    finally:
        if coordinator: await coordinator.close()
        if os.path.exists(DB_FILE): os.remove(DB_FILE)

if __name__ == "__main__":
    asyncio.run(main())


... [info] ✅ 翻译结果 original='Jaguar', translated='美洲虎', biz_id='wildlife.big_cat.jaguar'
... [info] ✅ 翻译结果 original='Jaguar', translated='捷豹', biz_id='automotive.brand.jaguar'


config = TransHubConfig(gc_retention_days=30) # 清理30天前未活跃的业务关联


# gc_demo.py
# ... (初始化 coordinator) ...
log.info("--- 运行垃圾回收 (GC) ---")

# 建议先进行“干跑”（dry_run=True），检查将要删除的内容
report = await coordinator.run_garbage_collection(dry_run=True, expiration_days=30)
log.info("GC 干跑报告", report=report)

# 确认无误后，再执行真正的删除
# await coordinator.run_garbage_collection(dry_run=False, expiration_days=30)


# rate_limiter_demo.py
from trans_hub.rate_limiter import RateLimiter
# ...

# 每秒补充 10 个令牌，桶的总容量为 100 个令牌
rate_limiter = RateLimiter(refill_rate=10, capacity=100)

coordinator = Coordinator(
    config=config,
    persistence_handler=handler,
    rate_limiter=rate_limiter # <-- 传入速率限制器
)
# ...


# fastapi_app.py
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Union

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationResult

log = structlog.get_logger(__name__)
coordinator: Coordinator

async def translation_processor_task():
    """健壮的后台任务，用于持续处理待翻译任务。"""
    while True:
        try:
            log.info("后台任务：开始检查待处理翻译...")
            # ... (循环处理所有目标语言) ...
            await asyncio.sleep(60)
        except Exception:
            log.error("后台翻译任务发生意外错误", exc_info=True)
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global coordinator
    setup_logging()
    
    apply_migrations("fastapi_app.db")
    log.info("数据库迁移完成。")
    
    config = TransHubConfig(database_url="sqlite:///fastapi_app.db", active_engine="openai")
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()

    task = asyncio.create_task(translation_processor_task())
    
    yield
    
    task.cancel()
    await coordinator.close()

app = FastAPI(lifespan=lifespan)

class TranslationRequestModel(BaseModel):
    text: str
    target_lang: str = "zh-CN"
    business_id: Optional[str] = None

@app.post("/translate", response_model=Union[TranslationResult, dict])
async def request_translation(request_data: TranslationRequestModel):
    """一个高效的翻译请求接口。"""
    existing_translation = await coordinator.get_translation(
        text_content=request_data.text, target_lang=request_data.target_lang
    )
    if existing_translation:
        return existing_translation

    await coordinator.request(
        target_langs=[request_data.target_lang],
        text_content=request_data.text,
        business_id=request_data.business_id,
        source_lang="en"
    )

    return {"status": "accepted", "detail": "Translation task has been queued."}

