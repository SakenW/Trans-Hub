# 指南 2：高级用法

欢迎来到 `Trans-Hub` 的高级用法指南！在您掌握了[快速入门](./01_quickstart.md)的基础之后，本指南将带您探索 `Trans-Hub` 更强大的功能，包括激活高级翻译引擎、处理上下文、管理数据生命周期以及与现代 Web 框架集成。

---

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
    得益于 `Trans-Hub` 的智能配置系统，您只需在创建 `TransHubConfig` 时，**声明您想使用的引擎**即可。无需手动创建任何子配置对象！

    ```python
    # a_script_with_openai.py
    from trans_hub.config import TransHubConfig
    # ... 其他导入与初始化代码 ...

    # --- 核心修改：只需一行代码即可激活 OpenAI ---
    config = TransHubConfig(active_engine="openai")

    # Coordinator 将自动使用 OpenAIEngine 及其从 .env 加载的配置
    coordinator = Coordinator(config=config, persistence_handler=handler)
    # ...
    ```

---

## **2. 来源追踪与情境翻译：`business_id` vs `context`**

在深入研究具体用法之前，理解 `Trans-Hub` 的两个核心概念至关重要：`business_id` 和 `context`。正确地使用它们，是发挥 `Trans-Hub` 全部能力的关键。

| 特性               | `business_id: str`                                                                  | `context: dict`                                                                                  |
| :----------------- | :---------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------- |
| **核心目的**       | **身份标识 (Identity)**                                                             | **翻译情境 (Circumstance)**                                                                      |
| **回答的问题**     | “这段文本**是什么**？” <br> “它**来自哪里**？”                                      | “应该**如何**翻译这段文本？”                                                                     |
| **主要作用**       | - **来源追踪**：将文本与业务实体关联。 <br> - **生命周期管理**：用于垃圾回收 (GC)。 | - **影响翻译结果**：为引擎提供额外信息。 <br> - **区分翻译版本**：不同上下文产生不同翻译。       |
| **对复用性的影响** | **促进复用**：不同 `business_id` 可以共享相同原文和上下文的翻译结果。               | **隔离翻译**：不同的 `context` 会生成不同的 `context_hash`，导致独立的翻译记录，**降低复用性**。 |
| **数据存储**       | `th_sources` 表                                                                     | `th_translations` 表 (`context_hash`, `context`)                                                 |
| **最佳实践**       | 用于稳定、唯一的业务标识，如 `ui.login.title` 或 `product_123_description`。        | 用于影响翻译质量的动态信息，如 `{"tone": "formal"}` 或 `{"text_type": "button_label"}`。         |

**一句话总结**: 使用 `business_id` 来管理你的文本资产，使用 `context` 来提升特定场景下的翻译质量。在实际应用中，我们**强烈推荐将两者结合使用**。

---

## **3. 上下文翻译：一词多义的艺术**

同一个词在不同语境下可能有不同的含义（例如 "Apple" 可以指水果或公司）。`Trans-Hub` 支持在翻译请求中添加 `context`，以实现更精准的本地化。

### **最佳实践**

与其粗暴地重写整个 prompt 模板，不如通过 `context` 为大语言模型提供**附加的系统级指令 (System Prompt)**。这更符合 `context` 的设计理念——“提供情境”，而不是“改变行为”。

_(注: 这需要对 `OpenAIEngine` 进行简单的修改以支持 `system_prompt`。这是一个推荐的自定义扩展。)_

### **示例**

假设我们要根据上下文翻译 "Apple"。

```python
# context_demo.py
# ... (使用上面为 OpenAI 准备的初始化代码) ...

async def main():
    coordinator = await initialize_trans_hub_for_openai()
    try:
        target_lang = "zh-CN"
        tasks = [
            {
                "text": "Apple",
                "context": {"system_prompt": "You are a professional translator specializing in fruits."},
                "business_id": "product.fruit.apple",
            },
            {
                "text": "Apple",
                "context": {"system_prompt": "You are a professional translator specializing in technology companies."},
                "business_id": "tech.company.apple_inc",
            },
        ]

        for task in tasks:
            await coordinator.request(
                target_langs=[target_lang], text_content=task['text'],
                context=task['context'], business_id=task['business_id'], source_lang='en'
            )

        log.info("正在处理所有待翻译任务...")
        results = [res async for res in coordinator.process_pending_translations(target_lang)]

        for result in results:
            log.info("翻译结果", result=result)
    finally:
        if coordinator: await coordinator.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### **预期输出**

`Trans-Hub` 通过 `context_hash` 将这两个请求视为独立的翻译任务并分别缓存。OpenAI 引擎会根据不同的 `system_prompt` 生成不同的结果。

- `result=... original_content='Apple', translated_content='苹果', ...`
- `result=... original_content='Apple', translated_content='苹果公司', ...`

---

## **4. 数据生命周期：使用垃圾回收 (GC)**

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
    log.info("--- 运行垃圾回收 (GC) ---")

    # 建议先进行“干跑”（dry_run=True），检查将要删除的内容
    report = await coordinator.run_garbage_collection(dry_run=True, expiration_days=30)
    log.info("GC 干跑报告", report=report)

    # 确认无误后，再执行真正的删除
    # await coordinator.run_garbage_collection(dry_run=False, expiration_days=30)
    ```

---

## **5. 速率限制：保护您的 API 密钥**

在 `Coordinator` 初始化时，传入一个 `RateLimiter` 实例即可。

```python
# rate_limiter_demo.py
from trans_hub.rate_limiter import RateLimiter
# ...

async def initialize_with_rate_limiter():
    # ...
    # 每秒补充 10 个令牌，桶的总容量为 100 个令牌
    rate_limiter = RateLimiter(refill_rate=10, capacity=100)

    coordinator = Coordinator(
        config=config,
        persistence_handler=handler,
        rate_limiter=rate_limiter # <-- 传入速率限制器
    )
    await coordinator.initialize()
    return coordinator
```

之后，`coordinator.process_pending_translations` 在每次调用翻译引擎前都会自动遵守此速率限制。

---

## **6. 集成到现代 Web 框架 (以 FastAPI 为例)**

`Trans-Hub` 的纯异步设计使其能与 FastAPI 等 ASGI 框架完美集成。

### **最佳实践**

将 `Coordinator` 作为一个**生命周期依赖项**，在应用启动时创建，在关闭时销毁。这样可以确保整个应用共享同一个 `Coordinator` 实例，从而共享其数据库连接池和缓存。

### **示例代码 (`fastapi_app.py`)**

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

log = structlog.get_logger(__name__)

# --- 全局 Coordinator 实例 ---
coordinator: Coordinator

async def translation_processor_task():
    """一个健壮的后台任务，用于持续处理待翻译任务。"""
    while True:
        try:
            log.info("后台任务：开始检查待处理翻译...")
            processed_count = 0
            # 在真实应用中，您可能需要更复杂的逻辑来处理所有语言
            async for _ in coordinator.process_pending_translations(target_lang="zh-CN"):
                processed_count += 1
            if processed_count > 0:
                log.info("后台任务：本轮处理完成", count=processed_count)
        except Exception:
            log.error("后台翻译任务发生意外错误，将在60秒后重试。", exc_info=True)

        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 在应用启动时执行 ---
    global coordinator
    setup_logging()

    db_path_str = "fastapi_app.db"
    apply_migrations(db_path_str)
    log.info("数据库迁移完成。")

    config = TransHubConfig(
        database_url=f"sqlite:///{db_path_str}",
        active_engine="openai"
    )
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()
    log.info("Trans-Hub Coordinator 初始化完成。")

    # 启动后台翻译任务
    task = asyncio.create_task(translation_processor_task())

    yield # 应用在此处运行

    # --- 在应用关闭时执行 ---
    task.cancel()
    await coordinator.close()
    log.info("Trans-Hub Coordinator 已关闭。")

app = FastAPI(lifespan=lifespan)

class TranslationRequestModel(BaseModel):
    text: str
    target_lang: str = "zh-CN"
    business_id: Optional[str] = None

@app.post("/translate", response_model=Union[TranslationResult, dict])
async def request_translation(request_data: TranslationRequestModel):
    """
    一个高效的翻译请求接口。
    - 如果已有翻译，立即返回。
    - 如果没有，则登记任务并返回“已接受”状态。
    """
    existing_translation = await coordinator.handler.get_translation(
        text_content=request_data.text,
        target_lang=request_data.target_lang
    )
    if existing_translation:
        return existing_translation

    await coordinator.request(
        target_langs=[request_data.target_lang],
        text_content=request_data.text,
        business_id=request_data.business_id,
        source_lang="en"
    )

    return {"status": "accepted", "detail": "Translation task has been queued for processing."}
```
