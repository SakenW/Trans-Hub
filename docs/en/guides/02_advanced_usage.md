# Guide 2: Advanced Usage

Welcome to the advanced usage guide of `Trans-Hub`! After you have mastered the basics in the [quick start](./01_quickstart.md), this guide will take you to explore the more powerful features of `Trans-Hub`.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. 激活高级引擎 (例如 OpenAI)**

当内置的免费引擎无法满足您的质量需求时，您可以无缝切换到更强大的引擎。

### **目标**

使用 OpenAI 的 GPT 模型作为翻译引擎，以获得更高的翻译质量。

### **步骤**

1.  **安装 OpenAI 依赖**:
    `Trans-Hub` 使用 `extras` 机制来管理可选依赖。

    ```bash
    pip install "trans-hub[openai]"
    ```

2.  **配置 `.env` 文件**:
    在您的项目根目录创建一个 `.env` 文件，并添加您的 OpenAI API 密钥和端点。`Trans-Hub` 会自动加载这些环境变量。

    ```dotenv
    # .env
    TH_OPENAI_ENDPOINT="https://api.openai.com/v1"
    TH_OPENAI_API_KEY="your-secret-openai-key"
    TH_OPENAI_MODEL="gpt-4o"
    ```

3.  **修改初始化代码**:
    得益于 `Trans-Hub` 的智能配置系统，您只需在创建 `TransHubConfig` 时，**声明您想使用的引擎**即可。

    ```python
    # a_script_with_openai.py
    from trans_hub.config import TransHubConfig
    # ... 其他导入与初始化代码 ...

    config = TransHubConfig(active_engine="openai", source_lang="en")
    coordinator = Coordinator(config=config, persistence_handler=handler)
    # ...
    ```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **2. Source Tracking and Contextual Translation: `business_id` vs `context`**

Before delving into the specific usage, it is crucial to understand the two core concepts of `Trans-Hub`: `business_id` and `context`.

| Feature | `business_id: str` | `context: dict` |
| :It seems there is no text provided for translation. Please provide the text you would like to have translated. | :It seems there is no text provided for translation. Please provide the text you would like to have translated. | :It seems there is no text provided for translation. Please provide the text you would like to have translated. |
| **Core Purpose** | **Identity** | **Circumstance** |
| **Questions Answered** | “What is this text **about**?” <br> “Where does it **come from**?” | “How should this text be **translated**?” |
| **Main Functions** | - **Source Tracking**: Associates text with business entities. <br> - **Lifecycle Management**: Used for garbage collection (GC). | - **Influences Translation Results**: Provides additional information to the engine. <br> - **Distinguishes Translation Versions**: Different contexts yield different translations. |
| **Impact on Reusability** | **Facilitates Reuse**: Different `business_id` can share the same original text and translation results. | **Isolates Translations**: Different `context` generates different `context_hash`, leading to independent translation records. |

**Summary in one sentence**: Use `business_id` to manage your text assets and use `context` to enhance translation quality in specific scenarios. We **strongly recommend using both together**.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. 上下文翻译实战：区分“捷豹”与“美洲虎”**

理论已经足够，让我们来看一个最能体现 `context` 威力的实战例子。同一个词 "Jaguar" 在不同语境下有完全不同的含义。我们将使用 `context` 来引导 OpenAI 引擎进行精确翻译。

### **示例代码 (`context_demo.py`)**

您可以将以下代码保存为一个文件并运行，亲眼见证上下文的力量。

```python
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
```

### **预期输出**

当你运行这段代码时，你会看到 `Trans-Hub` 为同一个原文 "Jaguar" 生成了两个完全不同的翻译：

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

`Trans-Hub` 内置的垃圾回收（GC）功能允许您定期清理数据库中过时或不再活跃的业务关联。

### **步骤**

1.  **配置保留期限**: 在 `TransHubConfig` 中设置 `gc_retention_days`。
    ```python
    config = TransHubConfig(gc_retention_days=30) # 清理30天前未活跃的业务关联
    ```
2.  **定期调用 GC**: 建议在独立的维护脚本或定时任务中执行。

    ```python
    # gc_demo.py
    # ... (初始化 coordinator) ...
    log.info("It seems there is no text provided for translation. Please provide the text you would like to have translated. 运行垃圾回收 (GC) It seems there is no text provided for translation. Please provide the text you would like to have translated.")

    # 建议先进行“干跑”（dry_run=True），检查将要删除的内容
    report = await coordinator.run_garbage_collection(dry_run=True, expiration_days=30)
    log.info("GC 干跑报告", report=report)

    # 确认无误后，再执行真正的删除
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