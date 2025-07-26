# 指南 2：高级用法

欢迎来到 `Trans-Hub` 的高级用法指南！在您掌握了[快速入门](./01_quickstart.md)的基础之后，本指南将带您探索 `Trans-Hub` 更强大的功能。

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
    得益于 `Trans-Hub` 的智能配置系统，您只需在创建 `TransHubConfig` 时，**声明您想使用的引擎**即可。

    ```python
    # a_script_with_openai.py
    from trans_hub.config import TransHubConfig
    # ... 其他导入与初始化代码 ...

    config = TransHubConfig(active_engine="openai", source_lang="en")
    coordinator = Coordinator(config=config, persistence_handler=handler)
    # ...
    ```

---

## **2. 来源追踪与情境翻译：`business_id` vs `context`**

在深入研究具体用法之前，理解 `Trans-Hub` 的两个核心概念至关重要：`business_id` 和 `context`。

| 特性 | `business_id: str` | `context: dict` |
| :--- | :--- | :--- |
| **核心目的** | **身份标识 (Identity)** | **翻译情境 (Circumstance)** |
| **回答的问题** | “这段文本**是什么**？” <br> “它**来自哪里**？” | “应该**如何**翻译这段文本？” |
| **主要作用** | - **来源追踪**：将文本与业务实体关联。 <br> - **生命周期管理**：用于垃圾回收 (GC)。 | - **影响翻译结果**：为引擎提供额外信息。 <br> - **区分翻译版本**：不同上下文产生不同翻译。 |
| **对复用性的影响** | **促进复用**：不同 `business_id` 可以共享相同原文和上下文的翻译结果。 | **隔离翻译**：不同的 `context` 会生成不同的 `context_hash`，导致独立的翻译记录。 |

**一句话总结**: 使用 `business_id` 来管理你的文本资产，使用 `context` 来提升特定场景下的翻译质量。我们**强烈推荐将两者结合使用**。

---

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
```

### **预期输出**

当你运行这段代码时，你会看到 `Trans-Hub` 为同一个原文 "Jaguar" 生成了两个完全不同的翻译：

```
... [info] ✅ 翻译结果 original='Jaguar', translated='美洲虎', biz_id='wildlife.big_cat.jaguar'
... [info] ✅ 翻译结果 original='Jaguar', translated='捷豹', biz_id='automotive.brand.jaguar'
```
这完美地展示了 `context` 如何通过 `context_hash` 隔离翻译记录，并通过 `system_prompt` 影响引擎的行为。

---

## **4. 综合演练：真实世界并发模拟**

我们已经分别介绍了 `Trans-Hub` 的各项高级功能。想看看它们在一个高并发、多任务的真实世界场景中如何协同工作吗？

我们提供了一个终极演示脚本，它同时运行内容生产者、后台翻译工作者和 API 查询服务。

👉 **[查看并运行 `examples/02_real_world_simulation.py`](../examples/02_real_world_simulation.py)**

这个“活文档”是理解 `Trans-Hub` 在真实世界中如何工作的最佳方式。

---
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
    log.info("--- 运行垃圾回收 (GC) ---")

    # 建议先进行“干跑”（dry_run=True），检查将要删除的内容
    report = await coordinator.run_garbage_collection(dry_run=True, expiration_days=30)
    log.info("GC 干跑报告", report=report)

    # 确认无误后，再执行真正的删除
    # await coordinator.run_garbage_collection(dry_run=False, expiration_days=30)
    ```

---

## **6. 速率限制：保护您的 API 密钥**

在 `Coordinator` 初始化时，传入一个 `RateLimiter` 实例即可。

```python
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
```

之后，`coordinator.process_pending_translations` 在每次调用翻译引擎前都会自动遵守此速率限制。

---

## **7. 集成到现代 Web 框架 (以 FastAPI 为例)**

`Trans-Hub` 的纯异步设计使其能与 FastAPI 等 ASGI 框架完美集成。

### **最佳实践**

将 `Coordinator` 作为一个**生命周期依赖项**，在应用启动时创建，在关闭时销毁。这样可以确保整个应用共享同一个 `Coordinator` 实例。

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
```