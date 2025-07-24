# 指南 2：高级用法

欢迎来到 `Trans-Hub` 的高级用法指南！在您掌握了[快速入门](./01_quickstart.md)的基础之后，本指南将带您探索 `Trans-Hub` 更强大的功能，包括激活高级翻译引擎、处理上下文、管理数据生命周期以及与现代 Web 框架集成。

---

## **1. 激活高级引擎 (例如 OpenAI)**

当内置的免费引擎无法满足您的质量需求时，您可以无缝切换到更强大的引擎。

### **目标**

使用 OpenAI 的 GPT 模型作为翻译引擎。

### **步骤**

1.  **安装 OpenAI 依赖**:
    `Trans-Hub` 使用 `extras` 机制来管理可选依赖。

    ```bash
    pip install "trans-hub[openai]"
    ```

2.  **配置 `.env` 文件**:
    在您的项目根目录创建一个 `.env` 文件，并添加您的 OpenAI API 密钥和端点。`Trans-Hub` 会自动加载这些环境变量。

    ```env
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

    async def initialize_trans_hub_for_openai():
        # ... (日志和数据库设置与快速入门相同) ...

        # --- 核心修改：只需一行代码即可激活 OpenAI ---
        config = TransHubConfig(active_engine="openai")

        coordinator = Coordinator(config=config, persistence_handler=handler)
        await coordinator.initialize()
        return coordinator
    ```

## **2. 上下文翻译：一词多义的艺术**

同一个词在不同语境下可能有不同的含义（例如 "Apple" 可以指水果或公司）。`Trans-Hub` 支持在翻译请求中添加 `context`，以实现更精准的本地化。

### **目标**

将 "Apple" 根据上下文分别翻译为“水果”和“公司”。

### **步骤**

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
                "context": {"prompt_template": "Translate the following fruit name: {text}"},
                "business_id": "product.fruit.apple",
            },
            {
                "text": "Apple",
                "context": {"prompt_template": "Translate the following company name: {text}"},
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

`Trans-Hub` 通过 `context_hash` 将这两个请求视为独立的翻译任务并分别缓存。

- `result=... original_content='Apple', translated_content='苹果', ...`
- `result=... original_content='Apple', translated_content='苹果公司', ...`

## **3. 数据生命周期：使用垃圾回收 (GC)**

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

## **4. 速率限制：保护您的 API 密钥**

在 `Coordinator` 初始化时，传入一个 `RateLimiter` 实例即可。

```python
# rate_limiter_demo.py
from trans_hub.rate_limiter import RateLimiter
# ...

async def initialize_with_rate_limiter():
    # ...
    # 每秒补充 1 个令牌，桶的总容量为 5 个令牌
    rate_limiter = RateLimiter(refill_rate=1, capacity=5)

    coordinator = Coordinator(
        config=config,
        persistence_handler=handler,
        rate_limiter=rate_limiter # <-- 传入速率限制器
    )
    await coordinator.initialize()
    return coordinator
```

之后，`coordinator.process_pending_translations` 在每次调用翻译引擎前都会自动遵守此速率限制。

## **5. 集成到现代 Web 框架 (以 FastAPI 为例)**

`Trans-Hub` 的纯异步设计使其能与 FastAPI 等 ASGI 框架完美集成。

### **最佳实践**

将 `Coordinator` 作为一个**生命周期依赖项**，在应用启动时创建，在关闭时销毁。这样可以确保整个应用共享同一个 `Coordinator` 实例，从而共享其数据库连接池和缓存。

### **示例代码 (`fastapi_app.py`)**

```python
# fastapi_app.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

# --- 1. 全局 Coordinator 实例 ---
# 它将在应用启动时被初始化
coordinator: Coordinator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 2. 在应用启动时执行 ---
    global coordinator
    setup_logging()
    config = TransHubConfig(active_engine="openai") # 假设使用 OpenAI
    handler = DefaultPersistenceHandler(db_path=config.db_path)
    coordinator = Coordinator(config=config, persistence_handler=handler)
    await coordinator.initialize()

    yield # 应用在此处运行

    # --- 3. 在应用关闭时执行 ---
    await coordinator.close()

app = FastAPI(lifespan=lifespan)

# --- 4. 后台任务：定期处理翻译 ---
async def process_all_translations():
    while True:
        # 在真实应用中，您可能需要更复杂的逻辑来处理所有语言
        async for _ in coordinator.process_pending_translations(target_lang="zh-CN"):
            pass # 循环直到所有任务处理完毕
        await asyncio.sleep(60) # 每60秒检查一次新任务

@app.on_event("startup")
async def startup_event():
    # 启动一个后台任务来处理翻译
    asyncio.create_task(process_all_translations())

@app.post("/translate")
async def translate_endpoint(text: str, target_lang: str, background_tasks: BackgroundTasks):
    """一个高效的翻译请求接口。"""

    # 1. 尝试直接从缓存获取
    cached_result = await coordinator.handler.get_translation(text, target_lang)
    if cached_result:
        return cached_result

    # 2. 缓存未命中，登记新任务
    await coordinator.request(target_langs=[target_lang], text_content=text)

    # 3. 告知客户端任务已接受
    return {"status": "accepted", "detail": "Translation task is being processed."}
```
