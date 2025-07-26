# Guide 2: Advanced Usage

Welcome to the advanced usage guide of `Trans-Hub`! After you have mastered the basics in the [quick start](./01_quickstart.md), this guide will take you to explore the more powerful features of `Trans-Hub`.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. Activate Advanced Engine (e.g., OpenAI)**

When the built-in free engine cannot meet your quality requirements, you can seamlessly switch to a more powerful engine.

### **Objective**

Use OpenAI's GPT model as a translation engine for higher translation quality.

### **Steps**

1. **Install OpenAI dependencies**:  
   `Trans-Hub` uses the `extras` mechanism to manage optional dependencies.

    ```bash
    pip install "trans-hub[openai]"
    ```

2. **Configure the `.env` file**:  
   Create a `.env` file in your project root directory and add your OpenAI API key and endpoint. `Trans-Hub` will automatically load these environment variables.

    ```dotenv
    # .env
    TH_OPENAI_ENDPOINT="https://api.openai.com/v1"
    TH_OPENAI_API_KEY="your-secret-openai-key"
    TH_OPENAI_MODEL="gpt-4o"
    ```

3. **Modify Initialization Code**: Thanks to the intelligent configuration system of `Trans-Hub`, you only need to **declare the engine you want to use** when creating `TransHubConfig`.

    ```python
    # a_script_with_openai.py
    from trans_hub.config import TransHubConfig
    # ... 其他导入与初始化代码 ...

    config = TransHubConfig(active_engine="openai", source_lang="en")
    coordinator = Coordinator(config=config, persistence_handler=handler)
    # ...

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **2. Source Tracking and Contextual Translation: `business_id` vs `context`**

Before delving into the specific usage, it is crucial to understand the two core concepts of `Trans-Hub`: `business_id` and `context`.

| 特性 | `business_id: str` | `context: dict` |
| :It seems there is no text provided for translation. Please provide the text you would like to have translated. | :It seems there is no text provided for translation. Please provide the text you would like to have translated. | :It seems there is no text provided for translation. Please provide the text you would like to have translated. |
| **核心目的** | **身份标识 (Identity)** | **翻译情境 (Circumstance)** |
| **回答的问题** | “这段文本**是什么**？” <br> “它**来自哪里**？” | “应该**如何**翻译这段文本？” |
| **主要作用** | - **来源追踪**：将文本与业务实体关联。 <br> - **生命周期管理**：用于垃圾回收 (GC)。 | - **影响翻译结果**：为引擎提供额外信息。 <br> - **区分翻译版本**：不同上下文产生不同翻译。 |
| **对复用性的影响** | **促进复用**：不同 `business_id` 可以共享相同原文和上下文的翻译结果。 | **隔离翻译**：不同的 `context` 会生成不同的 `context_hash`，导致独立的翻译记录。 |

**Summary in one sentence**: Use `business_id` to manage your text assets and use `context` to enhance translation quality in specific scenarios. We **strongly recommend using both together**.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. Contextual Translation Practice: Distinguishing "Jaguar" from "Puma"**

The theory is sufficient; let's look at a practical example that best demonstrates the power of `context`. The same word 'Jaguar' has completely different meanings in different contexts. We will use `context` to guide the OpenAI engine for precise translation.

### **Example Code (`context_demo.py`)**

You can save the following code as a file and run it to witness the power of context firsthand.

```python
import asyncio
import os
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Ensure trans_hub is in the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging

# It seems there is no text provided for translation. Please provide the text you would like to have translated. 准备工作 It seems there is no text provided for translation. Please provide the text you would like to have translated.
load_dotenv()
setup_logging()
log = structlog.get_logger()
DB_FILE = "context_demo.db"


async def main():
    # It seems there is no text provided for translation. Please provide the text you would like to have translated. 1. 初始化 It seems there is no text provided for translation. Please provide the text you would like to have translated.
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

        # It seems there is no text provided for translation. Please provide the text you would like to have translated. 2. 登记任务 It seems there is no text provided for translation. Please provide the text you would like to have translated.
        for task in tasks:
            await coordinator.request(
                target_langs=[target_lang], text_content=task['text'],
                context=task['context'], business_id=task['business_id']
            )

        # It seems there is no text provided for translation. Please provide the text you would like to have translated. 3. 处理并打印结果 It seems there is no text provided for translation. Please provide the text you would like to have translated.
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

### **Expected Output**

When you run this code, you will see that `Trans-Hub` generates two completely different translations for the same original text 'Jaguar':

```
... [info] ✅ 翻译结果 original='Jaguar', translated='美洲虎', biz_id='wildlife.big_cat.jaguar'
... [info] ✅ 翻译结果 original='Jaguar', translated='捷豹', biz_id='automotive.brand.jaguar'
```
这完美地展示了 `context` 如何通过 `context_hash` 隔离翻译记录，并通过 `system_prompt` 影响引擎的行为。

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **4. Comprehensive Drill: Real-World Concurrent Simulation**

We have introduced the various advanced features of `Trans-Hub` separately. Would you like to see how they work together in a real-world scenario with high concurrency and multiple tasks?

We provide an ultimate demonstration script that simultaneously runs content producers, backend translators, and API query services.

👉 **[View and run `examples/02_real_world_simulation.py`](../examples/02_real_world_simulation.py)**

This "living document" is the best way to understand how `Trans-Hub` works in the real world.

It seems there is no text provided for translation. Please provide the text you would like to have translated.
## **5. 数据生命周期：使用垃圾回收 (GC)**

The built-in garbage collection (GC) feature of `Trans-Hub` allows you to regularly clean up outdated or inactive business associations in the database.

### **Steps**

1.  **Retention Period Configuration**: Set `gc_retention_days` in `TransHubConfig`.
    ```python
    config = TransHubConfig(gc_retention_days=30) # Clean up business associations that have not been active for 30 days
    ```
2.  **Regularly Invoke GC**: It is recommended to execute it in a separate maintenance script or scheduled task.

    ```python
    # gc_demo.py
    # ... (初始化 coordinator) ...
    log.info("It seems there is no text provided for translation. Please provide the text you would like to have translated. 运行垃圾回收 (GC) It seems there is no text provided for translation. Please provide the text you would like to have translated.")

    # It is recommended to first perform a "dry run" (dry_run=True) to check the content to be deleted
    report = await coordinator.run_garbage_collection(dry_run=True, expiration_days=30)
    log.info("GC dry run report", report=report)

    # After confirming that there are no errors, proceed with the actual deletion
    # await coordinator.run_garbage_collection(dry_run=False, expiration_days=30)
    ```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **6. Rate Limiting: Protect Your API Key**

Pass a `RateLimiter` instance when initializing the `Coordinator`.

```python
# rate_limiter_demo.py
from trans_hub.rate_limiter import RateLimiter
# ...

# Replenish 10 tokens per second, with a total bucket capacity of 100 tokens
rate_limiter = RateLimiter(refill_rate=10, capacity=100)

coordinator = Coordinator(
    config=config,
    persistence_handler=handler,
    rate_limiter=rate_limiter # <-- Pass in the rate limiter
)
# ...

After that, `coordinator.process_pending_translations` will automatically comply with this rate limit before each call to the translation engine.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **7. Integration into Modern Web Frameworks (Taking FastAPI as an Example)**

The pure asynchronous design of `Trans-Hub` allows it to integrate perfectly with ASGI frameworks like FastAPI.

### **Best Practices**

Use `Coordinator` as a **lifecycle dependency**, created at application startup and destroyed at shutdown. This ensures that the entire application shares the same `Coordinator` instance.

### **Example Code (`fastapi_app.py`)**

```python
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

log = structlog.get_logger(__name__) coordinator: Coordinator

async def translation_processor_task():
    """Robust background task for continuously processing translation tasks."""
    while True:
        try:
            log.info("Background task: Starting to check for pending translations...")
            # ... (loop through all target languages) ...
            await asyncio.sleep(60)
        except Exception:
            log.error("An unexpected error occurred in the background translation task", exc_info=True)
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global coordinator
    setup_logging()
    
    apply_migrations("fastapi_app.db")
    log.info("Database migration completed.")
    
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

An efficient translation request interface.

    await coordinator.request(
        target_langs=[request_data.target_lang],
        text_content=request_data.text,
        business_id=request_data.business_id,
        source_lang="en"
    )

    return {"status": "accepted", "detail": "Translation task has been queued."}