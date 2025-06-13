# **Trans-Hub 实践指南 (Cookbook) 👨‍🍳**

欢迎来到 `Trans-Hub` Cookbook！这份指南旨在通过实用的代码示例和解释，帮助你快速上手并充分利用 `Trans-Hub` 的强大功能。无论你是想快速翻译几行文本，还是想在复杂的应用中实现智能本地化，这里都有适合你的“食谱”。

---

## **目录**

1.  [快速入门：你的第一个翻译任务](#1-快速入门你的第一个翻译任务)
2.  [升级引擎：从免费到强大 (例如 OpenAI)](#2-升级引擎从免费到强大-例如-openai)
3.  [智能缓存：工作原理与验证](#3-智能缓存工作原理与验证)
4.  [上下文翻译：一词多义的艺术](#4-上下文翻译一词多义的艺术)
5.  [数据生命周期：使用垃圾回收 (GC)](#5-数据生命周期使用垃圾回收-gc)
6.  [错误处理与重试策略](#6-错误处理与重试策略)
7.  [速率限制：保护你的 API 密钥](#7-速率限制保护你的-api-密钥)
8.  [异步工作流 (进阶)](#8-异步工作流-进阶)
9.  [集成到 Web 框架 (以 Flask 为例)](#9-集成到-web-框架-以-flask-为例)
10. [调试技巧：检查数据库内部状态](#10-调试技巧检查数据库内部状态)

---

## **1. 快速入门：你的第一个翻译任务**

这个食谱展示了如何用最少的配置，在几分钟内开始使用 `Trans-Hub`。

### **目标**

使用 `Trans-Hub` 的内置免费翻译引擎，将 "Hello, world!" 翻译成中文。

### **步骤**

1.  **安装 `Trans-Hub`**:

    ```bash
    pip install trans-hub
    ```

2.  **创建你的翻译脚本 (例如 `quick_start.py`)**:

    ```python
    # quick_start.py
    import os
    import structlog
    from dotenv import load_dotenv

    from trans_hub.config import EngineConfigs, TransHubConfig
    from trans_hub.coordinator import Coordinator
    from trans_hub.db.schema_manager import apply_migrations
    from trans_hub.logging_config import setup_logging
    from trans_hub.persistence import DefaultPersistenceHandler

    log = structlog.get_logger()
    DB_FILE = "quick_start_translations.db"

    def initialize_trans_hub():
        """一个标准的初始化函数。"""
        setup_logging(log_level="INFO")
        if not os.path.exists(DB_FILE):
            log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
            apply_migrations(DB_FILE)
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            engine_configs=EngineConfigs() # 默认使用 'translators' 免费引擎
        )
        return Coordinator(config=config, persistence_handler=handler)

    def main():
        """主程序入口。"""
        load_dotenv()
        coordinator = initialize_trans_hub()
        try:
            text_to_translate = "Hello, world!"
            target_language_code = "zh-CN"

            log.info("正在登记翻译任务...", text=text_to_translate, lang=target_language_code)
            coordinator.request(
                target_langs=[target_language_code],
                text_content=text_to_translate,
                business_id="app.greeting.hello_world"
            )

            log.info(f"正在处理 '{target_language_code}' 的待翻译任务...")
            results = list(coordinator.process_pending_translations(target_lang=target_language_code))

            if results:
                first_result = results[0]
                log.info(
                    "翻译完成！",
                    original=first_result.original_content,
                    translation=first_result.translated_content,
                    status=first_result.status.name,
                    engine=first_result.engine,
                    business_id=first_result.business_id
                )
            else:
                log.warning("没有需要处理的新任务（可能已翻译过）。")
        finally:
            if coordinator:
                coordinator.close()

    if __name__ == "__main__":
        main()
    ```

3.  **运行脚本**:
    ```bash
    python quick_start.py
    ```

### **预期输出**

你将看到类似如下的日志，显示 "Hello, world!" 被翻译成 "你好世界！"：

```
... [info     ] 正在登记翻译任务...
... [info     ] 正在处理 'zh-CN' 的待翻译任务...
... [info     ] 翻译完成！                           original=Hello, world! translation=你好世界！ status=TRANSLATED engine=translators business_id=app.greeting.hello_world
```

## **2. 升级引擎：从免费到强大 (例如 OpenAI)**

当内置的免费引擎无法满足你的质量或规模需求时，你可以轻松切换到更强大的引擎，如 OpenAI。

### **目标**

使用 OpenAI 翻译引擎。

### **步骤**

1.  **安装 OpenAI 依赖**:

    ```bash
    pip install "trans-hub[openai]"
    ```

2.  **配置 `.env` 文件**:
    在项目根目录创建 `.env` 文件，并添加你的 OpenAI API 密钥和可选的端点。

    ```env
    # .env
    TH_OPENAI_ENDPOINT="https://api.openai.com/v1" # 如果是 Azure OpenAI，需要修改
    TH_OPENAI_API_KEY="your-secret-openai-key"
    TH_OPENAI_MODEL="gpt-3.5-turbo" # 或其他模型，如 gpt-4
    ```

3.  **修改初始化代码**:
    在你脚本的 `initialize_trans_hub` 函数中，修改 `TransHubConfig` 的创建。

    ```python
    # ... (在你的初始化函数中)
    from trans_hub.engines.openai import OpenAIEngineConfig

    def initialize_trans_hub():
        # ... (其他代码不变) ...
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            active_engine="openai", # <-- 明确指定使用 openai 引擎
            engine_configs=EngineConfigs(
                openai=OpenAIEngineConfig() # <-- 创建实例以触发 .env 加载和配置验证
            )
        )
        # ...
    ```

4.  **运行脚本**，你将看到日志中的 `engine` 字段变为 `openai`。

## **3. 智能缓存：工作原理与验证**

`Trans-Hub` 自动缓存所有翻译结果。这个食谱将解释其工作原理，并教你如何验证缓存。

### **目标**

理解并验证 `Trans-Hub` 的缓存机制。

### **工作原理**

- **`request()`**: 当你请求一个翻译时，`Trans-Hub` 会检查数据库中是否已存在**相同内容、相同目标语言、相同上下文**的**已成功翻译**的记录。
- **`process_pending_translations()`**: 这个方法**只处理**状态为 `PENDING` 或 `FAILED` 的任务。如果一个翻译请求因为缓存命中而没有创建 `PENDING` 任务，这个方法自然就不会处理它。

### **步骤 1：观察缓存行为**

1.  **运行 `quick_start.py` 脚本**，它会进行一次真实的翻译并存入数据库。
2.  **不删除数据库文件**，再次运行 `quick_start.py`。

你会发现第二次运行时，日志会显示 `没有需要处理的新任务`。这正是缓存的体现！

### **步骤 2：显式查询缓存**

如果你想获取一个**已经翻译过**的结果（无论它是否在本次运行中被翻译），你需要直接从 `PersistenceHandler` 查询。

```python
# cache_query_demo.py
# ... (与 quick_start.py 类似的初始化代码) ...

def main():
    load_dotenv()
    coordinator = initialize_trans_hub()
    try:
        text_to_translate = "Hello, world!"
        target_lang = "zh-CN"

        # 确保翻译已存在于缓存中（可以先运行一次 quick_start.py）
        log.info("--- 直接查询缓存 ---")
        # 使用 coordinator.handler 的 get_translation 方法直接查询
        cached_result = coordinator.handler.get_translation(
            text_content=text_to_translate,
            target_lang=target_lang,
            context=None # 无上下文
        )

        if cached_result:
            log.info(
                "从缓存中获取结果！",
                original=cached_result.original_content,
                translation=cached_result.translated_content,
                from_cache=cached_result.from_cache # 应该为 True
            )
        else:
            log.error("缓存未命中！请先运行一次翻译来填充缓存。")
    finally:
        if coordinator:
            coordinator.close()

if __name__ == "__main__":
    main()
```

运行此脚本，你会看到日志明确地显示 `from_cache=True`。

## **4. 上下文翻译：一词多义的艺术**

同一个词在不同语境下可能有不同的含义。`Trans-Hub` 支持在翻译请求中添加上下文，以实现更精准的本地化。

### **目标**

翻译 "Apple" 作为“水果”和“公司”的两种不同含义。

### **步骤**

创建一个新脚本 `context_demo.py` 来演示。

```python
# context_demo.py
# ... (与 quick_start.py 类似的初始化代码，但建议使用新的 DB_FILE) ...

def main():
    load_dotenv()
    coordinator = initialize_trans_hub()
    try:
        target_lang = "zh-CN"
        tasks = [
            {
                "text": "Apple",
                "context": {"category": "fruit"}, # 上下文1：水果
                "business_id": "product.fruit.apple",
            },
            {
                "text": "Apple",
                "context": {"category": "company"}, # 上下文2：公司
                "business_id": "tech.company.apple_inc",
            },
        ]

        for task in tasks:
            coordinator.request(
                target_langs=[target_lang],
                text_content=task['text'],
                context=task['context'],
                business_id=task['business_id']
            )

        log.info(f"正在处理所有待翻译任务...")
        results = list(coordinator.process_pending_translations(target_lang=target_lang))

        for result in results:
            log.info(
                "翻译结果：",
                original=result.original_content,
                context_hash=result.context_hash,
                translation=result.translated_content,
                business_id=result.business_id,
            )
    finally:
        if coordinator:
            coordinator.close()

if __name__ == "__main__":
    main()
```

### **预期输出**

你会看到两条翻译结果，每条都有不同的 `context_hash`。

- **解读**：`Trans-Hub` 成功地将这两个请求视为独立的翻译任务并分别存储。翻译结果的质量取决于你所使用的翻译引擎。默认的 `translators` 引擎可能无法区分，但 **OpenAI 等高级引擎通常能根据上下文给出不同的翻译**（例如“苹果”和“苹果公司”）。

## **5. 数据生命周期：使用垃圾回收 (GC)**

`Trans-Hub` 内置的垃圾回收（GC）功能允许你定期清理数据库中过时或不再活跃的业务关联 (`th_sources` 表)。

### **目标**

演示如何配置和执行 GC，清理不再使用的 `business_id` 记录。

### **步骤**

1.  **修改初始化配置**:
    在 `TransHubConfig` 中设置 `gc_retention_days`。

    ```python
    # ...
    config = TransHubConfig(
        # ...
        gc_retention_days=30 # 例如，清理30天前未活跃的业务关联
    )
    # ...
    ```

2.  **在你的应用中定期调用 GC**:
    建议在独立的维护脚本或定时任务中执行此操作。

    ```python
    # ...
    log.info("--- 运行垃圾回收 (GC) ---")

    # 建议先进行“干跑”，检查将要删除的内容
    gc_report_dry_run = coordinator.run_garbage_collection(dry_run=True)
    log.info("GC 干跑报告：", report=gc_report_dry_run)

    # 确认无误后，再执行真正的删除
    # gc_report_actual = coordinator.run_garbage_collection(dry_run=False)
    # log.info("GC 实际执行报告：", report=gc_report_actual)
    ```

### **工作原理**

- 每次调用 `request(business_id=...)` 都会更新 `th_sources` 表中对应 `business_id` 的 `last_seen_at` 时间戳。
- `run_garbage_collection(retention_days=N)` 会删除所有 `last_seen_at` **日期**早于 N 天的记录。
- **特别说明 `retention_days=0`**: 这个设置意味着 GC 将会清理所有 `last_seen_at` **在今天之前**的记录，并**保留所有今天**被访问过的记录。因此，在一个单次运行的脚本中调用 GC，通常不会清理掉任何记录，因为它们都是“今天”创建的。
- **重要**：GC 清理的是**业务 ID 的关联** (`th_sources` 表)，通常不会删除 `th_translations` 中的翻译结果本身。这些翻译结果仍然可以作为缓存使用。

## **6. 错误处理与重试策略**

`Trans-Hub` 内置了指数退避的自动重试机制，以应对临时的 API 错误。

### **目标**

理解 `Trans-Hub` 如何处理翻译过程中的错误和重试。

### **工作原理**

- **配置**：你可以在 `coordinator.process_pending_translations` 方法中控制 `max_retries` 和 `initial_backoff`。
- **错误类型**：`Trans-Hub` 依赖翻译引擎返回的 `EngineError` 中的 `is_retryable` 标志来决定是否重试。
  - `is_retryable=True` (如 5xx 错误): 会自动重试。
  - `is_retryable=False` (如 4xx 认证错误): 不会重试，任务状态直接变为 `FAILED`。

当重试发生时，你会在日志中看到类似“批次中包含可重试的错误...将在退避后重试...”的信息。

## **7. 速率限制：保护你的 API 密钥**

对于有严格调用频率限制的付费翻译服务，速率限制器是必不可少的。

### **目标**

配置 `Trans-Hub` 以限制对翻译 API 的调用速率。

### **步骤**

在 `Coordinator` 初始化时，传入一个 `RateLimiter` 实例。

```python
from trans_hub.rate_limiter import RateLimiter

# ...
# 每秒允许 1 个请求，桶容量为 5 个请求
rate_limiter = RateLimiter(rate=1, burst=5)
coordinator = Coordinator(
    config=config,
    persistence_handler=handler,
    rate_limiter=rate_limiter # <-- 传入速率限制器
)
# ...
```

之后，`coordinator.process_pending_translations` 在每次调用翻译引擎前都会自动遵守此速率限制。

## **8. 异步工作流 (进阶)**

`Trans-Hub` 的 `BaseTranslationEngine` 提供了 `atranslate_batch` 异步方法，为未来更高并发的异步 `Coordinator` 奠定基础。

- **引擎开发者**: 在开发自定义引擎时，强烈建议实现 `atranslate_batch` 方法，并使用真正的异步客户端（如 `aiohttp`）来调用外部 API。
- **当前 `Coordinator`**: 请注意，目前 `Coordinator` 实例本身是同步的。未来的版本计划引入一个完全异步的 `AsyncCoordinator`，以充分利用异步引擎的性能。

## **9. 集成到 Web 框架 (以 Flask 为例)**

在 Web 应用中，你通常需要将 `Trans-Hub` 的 `Coordinator` 实例绑定到应用的生命周期。

### **目标**

在 Flask 应用中，实现一个高效的、非阻塞的翻译请求接口。

### **最佳实践**

Web 接口的职责应该是**快速响应**。因此，`process_pending_translations` **不应该**在请求处理线程中直接调用。正确的模式是：

1.  接口首先尝试从缓存中获取结果。
2.  如果缓存未命中，则 `request` 一个新任务。
3.  立即返回 `202 Accepted` 响应，告知客户端任务已接受。
4.  一个独立的**后台工作进程**（例如使用 Celery, RQ）周期性地调用 `process_pending_translations()` 来处理所有待办任务。

### **示例代码 (`app.py`)**

```python
# app.py
import os
import structlog
from flask import Flask, g, request, jsonify

# 导入 Trans-Hub 核心组件
from dotenv import load_dotenv
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

app = Flask(__name__)
setup_logging(log_level="INFO")
log = structlog.get_logger()
DB_FILE = "flask_app_translations.db"

# 在应用启动时初始化数据库
if not os.path.exists(DB_FILE):
    apply_migrations(DB_FILE)

def get_trans_hub_coordinator():
    """为每个请求提供一个 Coordinator 实例。"""
    if 'trans_hub_coordinator' not in g:
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(database_url=f"sqlite:///{DB_FILE}")
        g.trans_hub_coordinator = Coordinator(config=config, persistence_handler=handler)
    return g.trans_hub_coordinator

@app.teardown_appcontext
def teardown_trans_hub(exception):
    """请求结束后，关闭 Coordinator 及其资源。"""
    coordinator = g.pop('trans_hub_coordinator', None)
    if coordinator is not None:
        coordinator.close()

@app.route('/translate', methods=['POST'])
def translate_text():
    """一个高效的翻译请求接口。"""
    data = request.get_json()
    text = data.get('text')
    target_lang = data.get('target_lang', 'zh-CN')

    if not text:
        return jsonify({"error": "Missing 'text' parameter"}), 400

    coordinator = get_trans_hub_coordinator()
    try:
        # 1. 尝试直接从缓存获取
        cached_result = coordinator.handler.get_translation(text, target_lang, data.get('context'))
        if cached_result:
            log.info("直接从缓存中返回结果。")
            return jsonify(cached_result.model_dump()) # 使用 .model_dump() 转换为字典

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
    except Exception as e:
        log.error("翻译请求处理失败", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    load_dotenv()
    app.run(debug=True)
```

## **10. 调试技巧：检查数据库内部状态**

有时候，你可能想直接查看 `Trans-Hub` 在数据库中到底存储了什么。为此，我们提供了一个方便的辅助工具脚本。

### **目标**

使用 `tools/inspect_db.py` 脚本，以一种带解读的、人类可读的格式，打印出数据库中所有的翻译记录。

### **步骤**

1.  **运行一个演示脚本以生成数据**:
    首先，确保你已经运行了 `demo_complex_workflow.py`，它会生成一个 `my_complex_trans_hub_demo.db` 文件。

2.  **运行检查工具**:
    在项目的根目录下，执行以下命令：
    ```bash
    poetry run python tools/inspect_db.py
    ```

### **预期输出**

脚本会连接到数据库，并逐条打印出所有翻译记录的详细信息，包括 `original_content`, `translated_text`, `context_hash`, `business_id` 等，并附上每个字段的详细解读。这对于深入理解 `Trans-Hub` 的数据模型和调试特定问题非常有帮助。
