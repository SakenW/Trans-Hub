# **指南 2：高级用法**

欢迎来到 `Trans-Hub` 的高级用法指南！在您掌握了[快速入门](./01_quickstart.md)的基础之后，本指南将带您探索 `Trans-Hub` 更强大的功能，包括使用高级翻译引擎、处理上下文、管理数据生命周期以及集成到 Web 框架中。

---

## **1. 升级引擎：从免费到强大 (例如 OpenAI)**

当内置的免费引擎无法满足您的质量或规模需求时，您可以轻松切换到更强大的引擎，如 OpenAI。

### **目标**

使用 OpenAI 的 GPT 模型作为翻译引擎。

### **步骤**

1.  **安装 OpenAI 依赖**:
    `Trans-Hub` 使用 `extras` 机制来管理可选依赖。要使用 OpenAI 引擎，请安装 `openai` extra：

    ```bash
    pip install "trans-hub[openai]"
    ```

2.  **配置 `.env` 文件**:
    在您的项目根目录创建一个名为 `.env` 的文件，并添加您的 OpenAI API 密钥和端点。`Trans-Hub` 会自动加载这些环境变量。

    ```env
    # .env
    TH_OPENAI_ENDPOINT="https://api.openai.com/v1" # 如果您使用 Azure OpenAI 或其他代理，请修改此端点
    TH_OPENAI_API_KEY="your-secret-openai-key"
    TH_OPENAI_MODEL="gpt-3.5-turbo" # 或其他模型，如 gpt-4-turbo
    ```

3.  **修改初始化代码**:
    在您脚本的初始化函数中，修改 `TransHubConfig` 的创建方式，明确指定 `active_engine` 并提供其配置。

    ```python
    # a_script_with_openai.py
    from trans_hub.config import EngineConfigs, TransHubConfig
    from trans_hub.engines.openai import OpenAIEngineConfig
    # ... 其他导入与初始化代码 ...

    def initialize_trans_hub_for_openai():
        # ... (日志和数据库设置与快速入门相同) ...
        handler = DefaultPersistenceHandler(db_path="openai_translations.db")

        # 创建一个配置，并明确激活 'openai' 引擎
        config = TransHubConfig(
            active_engine="openai",
            engine_configs=EngineConfigs(
                # 创建 OpenAIEngineConfig 实例以触发 .env 加载和配置验证
                openai=OpenAIEngineConfig()
            )
        )

        coordinator = Coordinator(config=config, persistence_handler=handler)
        return coordinator

    # ... (在 main 函数中调用此初始化函数) ...
    ```

4.  **运行脚本**，您将看到日志中的 `engine` 字段变为 `openai`，并且翻译会由 OpenAI 完成，带来更高质量的翻译结果。

## **2. 上下文翻译：一词多义的艺术**

同一个词在不同语境下可能有不同的含义（例如 "Apple" 可以指水果或公司）。`Trans-Hub` 支持在翻译请求中添加 `context`，以实现更精准的本地化。

### **目标**

将 "Apple" 根据上下文分别翻译为“水果”和“公司”。

### **步骤**

```python
# context_demo.py
# ... (与上面类似的 OpenAI 初始化代码) ...

def main():
    load_dotenv()
    coordinator = initialize_trans_hub_for_openai()
    try:
        target_lang = "zh-CN"
        tasks = [
            {
                "text": "Apple",
                "context": {"prompt_template": "Translate the following fruit name from {source_lang} to {target_lang}: {text}"},
                "business_id": "product.fruit.apple",
            },
            {
                "text": "Apple",
                "context": {"prompt_template": "Translate the following company name from {source_lang} to {target_lang}: {text}"},
                "business_id": "tech.company.apple_inc",
            },
        ]

        for task in tasks:
            coordinator.request(
                target_langs=[target_lang],
                text_content=task['text'],
                context=task['context'],
                business_id=task['business_id'],
                source_lang='en' # 为 OpenAI 提供源语言
            )

        log.info("正在处理所有待翻译任务...")
        results = list(coordinator.process_pending_translations(target_lang=target_lang))

        for result in results:
            log.info(
                "翻译结果",
                original=result.original_content,
                translation=result.translated_content,
                business_id=result.business_id
            )
    finally:
        if 'coordinator' in locals() and coordinator:
            coordinator.close()

if __name__ == "__main__":
    main()
```

### **预期输出**

当使用 OpenAI 等高级引擎时，您会看到两条不同的翻译结果，例如：

- `original=Apple, translation=苹果, business_id=product.fruit.apple`
- `original=Apple, translation=苹果公司, business_id=tech.company.apple_inc`

`Trans-Hub` 通过 `context_hash` 将这两个请求视为独立的翻译任务并分别缓存。

## **3. 数据生命周期：使用垃圾回收 (GC)**

`Trans-Hub` 内置的垃圾回收（GC）功能允许您定期清理数据库中过时或不再活跃的业务关联 (`th_sources` 表)。

### **目标**

演示如何配置和执行 GC，清理不再使用的 `business_id` 记录。

### **步骤**

1.  **在配置中设置保留期限**:
    在 `TransHubConfig` 中设置 `gc_retention_days`。

    ```python
    config = TransHubConfig(
        gc_retention_days=30 # 例如，清理30天前未活跃的业务关联
    )
    ```

2.  **在您的应用中定期调用 GC**:
    建议在独立的维护脚本或定时任务中执行此操作。

    ```python
    # gc_demo.py
    # ... (初始化 coordinator) ...

    log.info("--- 运行垃圾回收 (GC) ---")

    # 建议先进行“干跑”（dry_run=True），检查将要删除的内容，而不会实际删除
    gc_report_dry_run = coordinator.run_garbage_collection(dry_run=True)
    log.info("GC 干跑报告", report=gc_report_dry_run)

    # 确认无误后，再执行真正的删除
    # gc_report_actual = coordinator.run_garbage_collection(dry_run=False)
    # log.info("GC 实际执行报告", report=gc_report_actual)
    ```

### **工作原理**

- 每次调用 `request(business_id=...)` 都会更新 `th_sources` 表中对应 `business_id` 的 `last_seen_at` 时间戳。
- `run_garbage_collection()` 会删除所有 `last_seen_at` **日期**早于指定保留天数的业务关联记录。
- **重要**: GC 清理的是**业务 ID 的关联** (`th_sources` 表)，通常不会删除 `th_translations` 中的翻译结果本身。这些翻译结果仍然可以作为缓存使用。

## **4. 速率限制：保护您的 API 密钥**

对于有严格调用频率限制的付费翻译服务，速率限制器是必不可少的。

### **目标**

配置 `Trans-Hub` 以限制对翻译 API 的调用速率。

### **步骤**

在 `Coordinator` 初始化时，传入一个 `RateLimiter` 实例。

```python
# rate_limiter_demo.py
from trans_hub.rate_limiter import RateLimiter
# ... (其他导入和初始化代码) ...

def initialize_with_rate_limiter():
    # ...
    handler = DefaultPersistenceHandler(db_path="rate_limit_demo.db")
    config = TransHubConfig()

    # **注意参数名已更新**
    # 每秒补充 1 个令牌，桶的总容量为 5 个令牌
    rate_limiter = RateLimiter(refill_rate=1, capacity=5)

    coordinator = Coordinator(
        config=config,
        persistence_handler=handler,
        rate_limiter=rate_limiter # <-- 传入速率限制器
    )
    return coordinator
```

之后，`coordinator.process_pending_translations` 在每次调用翻译引擎前都会自动遵守此速率限制，保护您的 API 密钥不被封禁。

## **5. 异步工作流的内部处理**

`Trans-Hub` 的架构设计考虑了对异步操作的支持，尤其是在与纯异步引擎（如 `OpenAIEngine`）交互时。

- **异步感知的 `Coordinator`**: 尽管 `Coordinator` 实例本身及其 `process_pending_translations` 方法是同步的，但它现在是**“异步感知”**的。
  - 当 `Coordinator` 检测到当前活动的引擎是一个纯异步引擎时，它会在内部**自动使用 `asyncio.run()`** 来执行该引擎的 `atranslate_batch` 异步方法。
  - 这意味着，**作为用户，您无需更改任何代码**。无论是驱动同步引擎还是异步引擎，您都可以用同样的方式调用 `coordinator.process_pending_translations()`。`Trans-Hub` 会在幕后为您处理异步的复杂性。

## **6. 集成到 Web 框架 (以 Flask 为例)**

在 Web 应用中，您通常需要将 `Trans-Hub` 的 `Coordinator` 实例绑定到应用的生命周期。

### **最佳实践**

Web 接口的职责应该是**快速响应**。因此，重量级的 `process_pending_translations` **不应该**在请求处理线程中直接调用。正确的模式是：

1.  接口首先尝试从缓存中获取结果。
2.  如果缓存未命中，则调用轻量级的 `request()` 登记一个新任务。
3.  立即返回 `202 Accepted` 响应，告知客户端任务已接受。
4.  一个独立的**后台工作进程**（例如使用 Celery, RQ,或简单的 `APScheduler`）周期性地调用 `process_pending_translations()` 来处理所有待办任务。

### **示例代码 (`flask_app.py`)**

```python
# flask_app.py
import os
import structlog
from flask import Flask, g, request, jsonify
from typing import Optional

# 导入 Trans-Hub 核心组件
from dotenv import load_dotenv
from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging
# 明确导入核心类型
from trans_hub.types import TranslationResult

app = Flask(__name__)
setup_logging(log_level="INFO")
log = structlog.get_logger()
DB_FILE = "flask_app_translations.db"

# 在应用启动时初始化数据库
if not os.path.exists(DB_FILE):
    apply_migrations(DB_FILE)

def get_trans_hub_coordinator():
    """为每个请求提供一个 Coordinator 实例，并绑定到 Flask 的 g 对象。"""
    if 'trans_hub_coordinator' not in g:
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}")
        g.trans_hub_coordinator = Coordinator(config=config, persistence_handler=handler)
    return g.trans_hub_coordinator

@app.teardown_appcontext
def teardown_trans_hub(exception):
    """在每个请求结束后，关闭 Coordinator 及其资源。"""
    coordinator = g.pop('trans_hub_coordinator', None)
    if coordinator is not None:
        coordinator.close()

@app.route('/translate', methods=['POST'])
def translate_text():
    """一个高效的翻译请求接口。"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request must be a JSON"}), 400

    text = data.get('text')
    target_lang = data.get('target_lang', 'zh-CN')

    if not text:
        return jsonify({"error": "Missing 'text' parameter"}), 400

    coordinator = get_trans_hub_coordinator()
    try:
        # 1. 尝试直接从缓存获取
        cached_result: Optional[TranslationResult] = coordinator.handler.get_translation(text, target_lang, data.get('context'))
        if cached_result and cached_result.translated_content:
            log.info("直接从缓存中返回结果。")
            return jsonify(cached_result.model_dump())

        # 2. 缓存未命中，登记新任务
        log.info("缓存未命中，正在登记翻译任务...")
        coordinator.request(
            target_langs=[target_lang],
            text_content=text,
            business_id=data.get('business_id'),
            context=data.get('context')
        )

        # 3. 告知客户端任务已接受，将在后台处理
        return jsonify({"message": "Translation task has been accepted and is being processed in the background."}), 202

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        log.error("翻译请求处理失败", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    load_dotenv()
    # 提示: 在生产环境中，应使用 Gunicorn 或 uWSGI 等 WSGI 服务器运行此应用。
    app.run(debug=True)
```
