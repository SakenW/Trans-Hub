好的，经过我们对 `Trans-Hub` 的持续优化，是时候将这些实践经验整理成一份实用的 `Cookbook` 了。这份文档将提供一系列具体、可操作的“食谱”，帮助用户快速掌握 `Trans-Hub` 的各项功能。

以下是为您准备的 `cookbook.md` 文档。它涵盖了从快速入门到高级特性的各种场景，并强调了我们最新迭代中优化过的核心概念。

---

# **Trans-Hub 实践指南 (Cookbook) 👨‍🍳**

欢迎来到 `Trans-Hub` Cookbook！这份指南旨在通过实用的代码示例和解释，帮助你快速上手并充分利用 `Trans-Hub` 的强大功能。无论你是想快速翻译几行文本，还是想在复杂的应用中实现智能本地化，这里都有适合你的“食谱”。

---

## **目录**
1.  [快速入门：你的第一个翻译任务](#1-快速入门你的第一个翻译任务)
2.  [升级引擎：从免费到强大 (例如 OpenAI)](#2-升级引擎从免费到强大-例如-openai)
3.  [智能缓存：如何工作与优化](#3-智能缓存如何工作与优化)
4.  [上下文翻译：一词多义的艺术](#4-上下文翻译一词多义的艺术)
5.  [数据生命周期：使用垃圾回收 (GC)](#5-数据生命周期使用垃圾回收-gc)
6.  [错误处理与重试策略](#6-错误处理与重试策略)
7.  [速率限制：保护你的 API 密钥](#7-速率限制保护你的-api-密钥)
8.  [异步工作流 (进阶)](#8-异步工作流-进阶)
9.  [集成到 Web 框架 (以 Flask 为例)](#9-集成到-web-框架-以-flask-为例)
10. [日志与可观测性：深入洞察](#10-日志与可观测性深入洞察)

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
    from trans_hub.config import TransHubConfig, EngineConfigs
    from trans_hub.coordinator import Coordinator
    from trans_hub.db.schema_manager import apply_migrations
    from trans_hub.persistence import DefaultPersistenceHandler
    from trans_hub.logging_config import setup_logging
    from trans_hub.types import TranslationStatus

    log = structlog.get_logger()
    DB_FILE = "quick_start_translations.db"

    def initialize_trans_hub():
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
        load_dotenv()
        coordinator = initialize_trans_hub()
        try:
            text_to_translate = "Hello, world!"
            target_language_code = "zh-CN"

            log.info("正在登记翻译任务", text=text_to_translate, lang=target_language_code)
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
                    status=first_result.status,
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
... [info     ] 正在登记翻译任务                    text=Hello, world! lang=zh-CN
... [info     ] 为 content_id=1 确保了 1 个新的 PENDING 任务。
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
    在项目根目录创建 `.env` 文件，并添加你的 OpenAI API 密钥和可选的端点（如果你使用自定义端点）。
    ```env
    # .env
    TH_OPENAI_ENDPOINT="https://api.openai.com/v1" # 如果是 Azure OpenAI，需要修改
    TH_OPENAI_API_KEY="your-secret-openai-key"
    TH_OPENAI_MODEL="gpt-3.5-turbo" # 或其他模型，如 gpt-4
    ```

3.  **修改初始化代码**:
    在你的初始化函数（如 `quick_start.py` 中的 `initialize_trans_hub`）中，明确指定 `active_engine` 为 `"openai"`，并实例化 `OpenAIEngineConfig`。

    ```python
    # quick_start.py (部分修改)
    from trans_hub.config import TransHubConfig, EngineConfigs
    from trans_hub.engines.openai import OpenAIEngineConfig # 导入 OpenAI 引擎配置

    def initialize_trans_hub():
        # ... (其他代码不变) ...
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            active_engine="openai", # <-- 明确指定使用 openai 引擎
            engine_configs=EngineConfigs(
                openai=OpenAIEngineConfig() # <-- 创建实例以触发 .env 加载和配置验证
            )
        )
        return Coordinator(config=config, persistence_handler=handler)
    ```

4.  **运行脚本**:
    ```bash
    python quick_start.py
    ```

### **预期输出**

你会看到类似的输出，但 `engine` 字段现在将显示 `openai`。

```
... [info     ] 翻译完成！                           original=Hello, world! translation=你好世界！ status=TRANSLATED engine=openai business_id=app.greeting.hello_world
```

## **3. 智能缓存：如何工作与优化**

`Trans-Hub` 自动缓存所有翻译结果到本地数据库。这意味着重复的翻译请求会立即从缓存返回，大大降低 API 调用成本和响应时间。

### **目标**
演示缓存如何防止重复的 API 调用。

### **步骤**

1.  **确保你使用了 `quick_start.py` 中的初始配置**（即使用 `translators` 免费引擎，它会真正调用外部 API）。
2.  **首次运行 `quick_start.py`**:
    ```bash
    # 第一次运行，会发生实际翻译
    python quick_start.py
    ```
    观察日志，会看到实际的翻译过程。

3.  **再次运行 `quick_start.py` (不删除数据库文件)**:
    ```bash
    # 第二次运行，应该从缓存返回
    python quick_start.py
    ```

### **预期输出**

*   **第一次运行**：你会看到翻译过程的日志，显示 `engine=translators` 和 `source=新翻译`。
*   **第二次运行**：日志中会显示 `为 content_id=1 未创建新的 PENDING 任务 (可能已存在或已翻译)。`，并且 `没有需要处理的新任务。`
    *   **解读**：`coordinator.request` 发现该任务已存在并为 `TRANSLATED` 状态，因此没有创建新的 `PENDING` 任务。`process_pending_translations` 也因此没有找到任何新的任务需要处理。这正是缓存的体现：一旦翻译完成并缓存，`Trans-Hub` 不会再重新翻译。
    *   如果你希望在**每次 `process_pending_translations` 运行时都能得到 `TranslationResult` 对象（无论是否来自缓存）**，你需要通过 `coordinator.get_translation_result()` 接口来获取（此接口不在 `main.py` 示例中），而不是仅仅依赖 `process_pending_translations` 来获取 `PENDING` 任务。`Trans-Hub` 的核心是处理“待办”任务，而缓存的本质是避免“待办”。

## **4. 上下文翻译：一词多义的艺术**

同一个词在不同语境下可能有不同的含义。`Trans-Hub` 支持在翻译请求中添加上下文，以实现更精准的本地化。

### **目标**
翻译 "Apple" 作为“水果”和“公司”的两种不同含义。

### **步骤**

1.  **修改你的脚本 (例如 `context_demo.py`)**:
    ```python
    # context_demo.py
    import os
    import structlog
    from dotenv import load_dotenv
    from trans_hub.config import TransHubConfig, EngineConfigs
    from trans_hub.coordinator import Coordinator
    from trans_hub.db.schema_manager import apply_migrations
    from trans_hub.persistence import DefaultPersistenceHandler
    from trans_hub.logging_config import setup_logging
    from trans_hub.types import TranslationStatus

    log = structlog.get_logger()
    DB_FILE = "context_demo_translations.db"

    def initialize_trans_hub():
        setup_logging(log_level="INFO")
        if os.path.exists(DB_FILE): # 每次运行前删除，确保是新数据
            os.remove(DB_FILE)
            log.info(f"已删除旧数据库文件: {DB_FILE}")
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            engine_configs=EngineConfigs()
        )
        return Coordinator(config=config, persistence_handler=handler)

    def main():
        load_dotenv()
        coordinator = initialize_trans_hub()
        try:
            target_language_code = "zh-CN"

            tasks = [
                {
                    "text": "Apple",
                    "context": {"category": "fruit"}, # 上下文1：水果
                    "business_id": "product.fruit.apple",
                    "purpose": "苹果（水果）"
                },
                {
                    "text": "Apple",
                    "context": {"category": "company"}, # 上下文2：公司
                    "business_id": "tech.company.apple_inc",
                    "purpose": "苹果（公司）"
                },
                {
                    "text": "Bank",
                    "context": {"type": "financial_institution"}, # 上下文3：金融机构
                    "business_id": "finance.building.bank_branch",
                    "purpose": "银行（金融）"
                },
                {
                    "text": "Bank",
                    "context": {"type": "geographical_feature"}, # 上下文4：地理特征
                    "business_id": "geography.nature.river_bank",
                    "purpose": "河岸（地理）"
                },
            ]

            for task in tasks:
                log.info(f"正在登记任务: {task['purpose']}",
                         text=task['text'], context=task['context'], lang=target_language_code)
                coordinator.request(
                    target_langs=[target_language_code],
                    text_content=task['text'],
                    context=task['context'],
                    business_id=task['business_id']
                )

            log.info(f"正在处理所有待翻译任务到 '{target_language_code}'...")
            results = list(coordinator.process_pending_translations(target_lang=target_language_code))
            
            for result in results:
                log.info(
                    "翻译结果：",
                    original=result.original_content,
                    context=result.context_hash, # 显示上下文哈希
                    translation=result.translated_content,
                    status=result.status.name,
                    engine=result.engine,
                    business_id=result.business_id,
                    source="新翻译"
                )
        finally:
            if coordinator:
                coordinator.close()

    if __name__ == "__main__":
        main()
    ```

2.  **运行脚本**:
    ```bash
    python context_demo.py
    ```

### **预期输出**

你会看到四条翻译结果，每条都有不同的 `context_hash`。

```
... [info     ] 翻译结果：                          original=Apple context=266db3... translation=苹果 status=TRANSLATED engine=translators business_id=product.fruit.apple source=新翻译
... [info     ] 翻译结果：                          original=Apple context=17e93... translation=苹果 status=TRANSLATED engine=translators business_id=tech.company.apple_inc source=新翻译
... [info     ] 翻译结果：                          original=Bank context=9db07... translation=银行 status=TRANSLATED engine=translators business_id=finance.building.bank_branch source=新翻译
... [info     ] 翻译结果：                          original=Bank context=50da7... translation=银行 status=TRANSLATED engine=translators business_id=geography.nature.river_bank source=新翻译
```

*   **解读**：你会发现 `Apple` 的两次翻译结果可能都是“苹果”，`Bank` 都是“银行”。这表明默认的 `translators` 引擎对这些特定的上下文可能没有足够的能力进行区分翻译。但是，`Trans-Hub` 已经**成功地将这些带上下文的请求视为独立任务并存储**。
*   **优化**：如果你切换到 **OpenAI 引擎**并重新运行，你很可能会看到 "Apple" 被翻译成“苹果公司”，而 "Bank" 被翻译成“河岸”，这取决于 OpenAI 的模型能力。这是 `Trans-Hub` 插件化架构的优势：无需改变核心逻辑，即可提升翻译质量。

## **5. 数据生命周期：使用垃圾回收 (GC)**

`Trans-Hub` 内置的垃圾回收（GC）功能允许你定期清理数据库中过时或不再活跃的业务关联 (`th_sources` 表)。

### **目标**
演示如何配置和执行 GC，清理不再使用的 `business_id` 记录。

### **步骤**

1.  **修改初始化配置**：
    在你的脚本（例如 `quick_start.py`）中，修改 `initialize_trans_hub` 函数，将 `gc_retention_days` 设置为一个小值（例如 `0`，表示任何不是**本次运行中**被 `request` 的 `business_id` 都可能被清理）。

    ```python
    # quick_start.py (initialize_trans_hub 部分修改)
    DB_FILE = "gc_demo_translations.db"
    GC_RETENTION_DAYS_FOR_DEMO = 0 # 设为 0 天，便于演示效果

    def initialize_trans_hub():
        setup_logging(log_level="INFO")
        if os.path.exists(DB_FILE): # 每次运行前删除，确保一个干净的起点
            os.remove(DB_FILE)
            log.info(f"已删除旧数据库文件: {DB_FILE}")
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            engine_configs=EngineConfigs(),
            gc_retention_days=GC_RETENTION_DAYS_FOR_DEMO # <-- 应用 GC 配置
        )
        return Coordinator(config=config, persistence_handler=handler)
    ```

2.  **在 `main` 函数中添加 GC 逻辑**：
    我们将添加一个 `business_id` 在第一个 `request` 之后不再被 `request`，从而在 GC 运行时被标记为“过期”。

    ```python
    # quick_start.py (main 函数部分修改)
    def main():
        load_dotenv()
        coordinator = initialize_trans_hub()
        try:
            # 首次请求，这个 business_id 将被创建
            coordinator.request(
                target_langs=["zh-CN"],
                text_content="This is an old feature message.",
                business_id="legacy.feature.old_message"
            )
            coordinator.process_pending_translations(target_lang="zh-CN")
            log.info("旧功能消息已登记并处理。")

            # 再次请求一个不同的 business_id，旧的 business_id 不再被 'request'
            coordinator.request(
                target_langs=["zh-CN"],
                text_content="This is a new feature message.",
                business_id="new.feature.message"
            )
            coordinator.process_pending_translations(target_lang="zh-CN")
            log.info("新功能消息已登记并处理。")

            # --- 运行垃圾回收 ---
            log.info("\n=== 运行垃圾回收 (GC) ===")
            log.info(f"配置的 GC 保留天数: {GC_RETENTION_DAYS_FOR_DEMO} 天。")

            log.info("第一次运行 GC (干跑模式: dry_run=True)...")
            gc_report_dry_run = coordinator.run_garbage_collection(retention_days=GC_RETENTION_DAYS_FOR_DEMO, dry_run=True)
            log.info("GC 干跑报告：", report=gc_report_dry_run)
            if gc_report_dry_run["deleted_sources"] > 0:
                log.info(f"预估将删除 {gc_report_dry_run['deleted_sources']} 条源记录。")
                log.info(f"其中应该包含 'legacy.feature.old_message'。")
            else:
                log.info("没有源记录被报告为可删除。")

            log.info("\n--- 实际执行 GC ---")
            gc_report_actual = coordinator.run_garbage_collection(retention_days=GC_RETENTION_DAYS_FOR_DEMO, dry_run=False)
            log.info("GC 实际执行报告：", report=gc_report_actual)
            if gc_report_actual["deleted_sources"] > 0:
                log.info(f"实际已删除 {gc_report_actual['deleted_sources']} 条源记录。")
                log.info("请检查数据库文件，'legacy.feature.old_message' 相关的 th_sources 记录应该已被删除。")
            else:
                log.info("没有源记录被删除。")
            
            # --- 验证 GC 后再次请求 ---
            log.info("\n=== 验证 GC 后再次请求旧的 business_id ===")
            # 再次请求旧的 business_id，此时 th_sources 中它已被删除
            # request 会重新创建 th_sources 记录，但翻译结果可能还在 th_translations 中
            coordinator.request(
                target_langs=["zh-CN"],
                text_content="This is an old feature message.",
                business_id="legacy.feature.old_message"
            )
            log.info("再次处理 'legacy.feature.old_message' 任务...")
            results = list(coordinator.process_pending_translations(target_lang="zh-CN"))
            if results:
                log.info(
                    "再次请求结果：",
                    original=results[0].original_content,
                    translation=results[0].translated_content,
                    business_id=results[0].business_id,
                    source="从缓存获取" if results[0].from_cache else "新翻译"
                )
                log.info(f"注意：'business_id' '{results[0].business_id}' 在 th_sources 中的 last_seen_at 已被更新。")
            else:
                log.warning("再次请求的任务没有结果。")

        finally:
            if coordinator:
                coordinator.close()
    ```

3.  **运行脚本**:
    ```bash
    python quick_start.py # 或者你新建的 demo 文件
    ```

### **预期输出**

*   你将看到 `legacy.feature.old_message` 在 GC `dry_run` 和实际执行中被报告为可删除。
*   在 `GC_RETENTION_DAYS_FOR_DEMO = 0` 的设置下，除了最后一次 `request` (新功能消息) 的 `business_id` 外，其他所有 `business_id` 都应该被清理。
*   最后，当你再次 `request` `legacy.feature.old_message` 时，`th_sources` 表中会重新创建这条记录，并且 `process_pending_translations` 将快速从 `th_translations` 缓存中返回翻译结果。

## **6. 错误处理与重试策略**

`Trans-Hub` 内置了指数退避的自动重试机制，以应对临时的 API 错误。

### **目标**
理解 `Trans-Hub` 如何处理翻译过程中的错误和重试。

### **步骤**

由于模拟外部 API 的瞬时错误在 Cookbook 中难以实现，我们在此仅通过解释 `Trans-Hub` 的配置和行为来理解。

1.  **配置重试参数**:
    在 `coordinator.process_pending_translations` 方法中，你可以控制 `max_retries` 和 `initial_backoff`。
    ```python
    # coordinator.process_pending_translations(target_lang="zh-CN", max_retries=3, initial_backoff=0.5)
    ```
    *   `max_retries`: 最大重试次数（默认为 2）。
    *   `initial_backoff`: 首次重试的等待时间（秒，默认为 1.0）。后续重试的等待时间会指数级增长（`initial_backoff * (2 ** attempt)`）。

2.  **错误类型**:
    `Trans-Hub` 依赖翻译引擎返回的 `EngineError` 中的 `is_retryable` 标志来决定是否重试。
    *   **`is_retryable=True`**: 通常是瞬时错误（如网络问题、服务过载、5xx 状态码），`Trans-Hub` 会自动重试。
    *   **`is_retryable=False`**: 通常是永久性错误（如认证失败、4xx 状态码、无效参数），`Trans-Hub` 不会重试，任务状态直接变为 `FAILED`。

### **预期行为**

当翻译引擎返回 `EngineError(is_retryable=True)` 时，你会在日志中看到类似如下的输出：

```
... [warning  ] 批次中包含可重试的错误 (尝试次数: 1/3)。将在退避后重试批次...
... [info     ] 退避 1.00 秒后重试...
... [warning  ] 批次中包含可重试的错误 (尝试次数: 2/3)。将在退避后重试批次...
... [info     ] 退避 2.00 秒后重试...
... [error    ] 已达到最大重试次数 (2)，放弃当前批次的重试。
```

## **7. 速率限制：保护你的 API 密钥**

对于有严格调用频率限制的付费翻译服务，速率限制器是必不可少的。

### **目标**
配置 `Trans-Hub` 以限制对翻译 API 的调用速率。

### **步骤**

1.  **修改初始化代码**:
    在 `initialize_trans_hub` 函数中，实例化 `RateLimiter` 并将其传入 `Coordinator`。

    ```python
    # quick_start.py (initialize_trans_hub 部分修改)
    from trans_hub.rate_limiter import RateLimiter # 导入速率限制器

    def initialize_trans_hub():
        # ... (其他代码不变) ...
        handler = DefaultPersistenceHandler(db_path=DB_FILE)
        config = TransHubConfig(
            database_url=f"sqlite:///{DB_FILE}",
            active_engine="openai", # 通常对付费引擎才需要速率限制
            engine_configs=EngineConfigs(
                openai=OpenAIEngineConfig()
            )
        )
        # 每秒允许 1 个请求，桶容量为 5 个请求
        rate_limiter = RateLimiter(rate=1, burst=5) # 例如，每秒1次，可以突发5次
        return Coordinator(config=config, persistence_handler=handler, rate_limiter=rate_limiter) # <-- 传入速率限制器
    ```

2.  **模拟大量请求**:
    在 `main` 函数中添加一个循环，发送大量翻译请求。

    ```python
    # quick_start.py (main 函数部分修改)
    def main():
        load_dotenv()
        coordinator = initialize_trans_hub()
        try:
            target_language_code = "zh-CN"
            texts = [f"This is sentence number {i}." for i in range(20)] # 20个句子

            for i, text in enumerate(texts):
                coordinator.request(
                    target_langs=[target_language_code],
                    text_content=text,
                    business_id=f"app.sentence.{i}"
                )
            
            log.info("所有请求已登记。开始处理翻译任务，观察速率限制器...")
            # process_pending_translations 会在调用引擎前请求令牌
            results = list(coordinator.process_pending_translations(target_lang=target_language_code))
            
            for result in results:
                log.info(f"翻译完成: {result.original_content[:20]}... -> {result.translated_content[:20]}...")
        finally:
            if coordinator:
                coordinator.close()
    ```

### **预期输出**

你会看到日志中出现 `正在等待速率限制器令牌...` 和 `已获取速率限制器令牌，继续执行翻译。` 的信息。当请求速率过快时，程序会暂停，等待令牌桶中生成新的令牌，从而确保 API 调用频率在你的限制范围内。

## **8. 异步工作流 (进阶)**

`Trans-Hub` 的 `BaseTranslationEngine` 提供了 `atranslate_batch` 异步方法，为未来更高并发的异步 `Coordinator` 奠定基础。

### **目标**
了解 `Trans-Hub` 异步能力的当前状态和未来方向。

### **步骤**

1.  **引擎的异步实现**:
    当你开发自定义引擎时（参阅 `developing-engines.md`），请务必实现 `atranslate_batch` 方法，并使用真正的异步客户端（如 `aiohttp`）来调用外部 API。

    ```python
    # your_engine.py (示例片段)
    import aiohttp # 假设使用 aiohttp

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[YourContext] = None,
    ) -> List[EngineBatchItemResult]:
        async with aiohttp.ClientSession() as session:
            # 实际的异步 API 调用
            # response = await session.post(self.config.endpoint, json={...})
            # translated_text = await response.json()
            pass # 占位符
        return [EngineSuccess(translated_text="异步翻译结果")] * len(texts)
    ```

2.  **当前 `Coordinator` 的限制**:
    请注意，**目前 `Coordinator` 实例本身是同步的**。即使你的引擎实现了 `atranslate_batch`，`Coordinator` 的 `process_pending_translations` 方法目前仍然会调用引擎的同步 `translate_batch` 方法。
    *   **未来展望**：`Trans-Hub` 的未来版本计划引入一个完全异步的 `Coordinator` (`AsyncCoordinator`)，它将充分利用引擎的 `atranslate_batch` 方法，从而实现非阻塞的、高并发的翻译工作流，尤其适用于 Web 服务。

## **9. 集成到 Web 框架 (以 Flask 为例)**

在 Web 应用中，你通常需要将 `Trans-Hub` 的 `Coordinator` 实例绑定到应用的生命周期，例如在每个请求开始时可用，并在请求结束时清理资源。

### **目标**
在 Flask 应用中使用 `Trans-Hub`。

### **步骤**

1.  **创建 Flask 应用文件 (例如 `app.py`)**:

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
    from trans_hub.types import TranslationStatus

    # 初始化 Flask 应用
    app = Flask(__name__)

    # 配置日志 (与 main.py 相同)
    setup_logging(log_level="INFO")
    log = structlog.get_logger()

    # 数据库文件路径
    DB_FILE = "flask_app_translations.db"

    # --- 应用启动时初始化数据库 ---
    # 在生产环境中，迁移通常在部署脚本中执行，而不是每次应用启动时。
    # 但为方便演示，这里简化处理。
    if not os.path.exists(DB_FILE):
        log.info("Flask 应用: 数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)

    def get_trans_hub_coordinator():
        """为每个请求提供一个 Coordinator 实例 (如果尚未创建)。"""
        if 'trans_hub_coordinator' not in g:
            log.debug("Flask 应用: 正在创建新的 Coordinator 实例...")
            # 在 Web 环境中，通常会使用一个共享的持久化处理器或连接池
            # 这里为简化，每次都创建新的 DefaultPersistenceHandler
            handler = DefaultPersistenceHandler(db_path=DB_FILE)
            config = TransHubConfig(
                database_url=f"sqlite:///{DB_FILE}",
                engine_configs=EngineConfigs()
            )
            g.trans_hub_coordinator = Coordinator(config=config, persistence_handler=handler)
        return g.trans_hub_coordinator

    @app.teardown_appcontext
    def teardown_trans_hub(exception):
        """请求结束后，关闭 Coordinator 及其资源。"""
        coordinator = g.pop('trans_hub_coordinator', None)
        if coordinator is not None:
            log.debug("Flask 应用: 正在关闭 Coordinator 实例...")
            coordinator.close()

    @app.route('/translate', methods=['POST'])
    def translate_text():
        data = request.get_json()
        text_content = data.get('text')
        target_lang = data.get('target_lang', 'zh-CN')
        business_id = data.get('business_id')
        context = data.get('context')

        if not text_content:
            return jsonify({"error": "Missing 'text' parameter"}), 400

        coordinator = get_trans_hub_coordinator()

        try:
            # 登记翻译任务
            coordinator.request(
                target_langs=[target_lang],
                text_content=text_content,
                business_id=business_id,
                context=context
            )
            
            # 处理待翻译任务 (在实际 Web 应用中，这通常是后台任务，不在此处阻塞请求)
            # 为演示方便，这里同步处理
            processed_results = list(coordinator.process_pending_translations(target_lang=target_lang))

            if processed_results:
                # 返回第一个结果
                result = processed_results[0]
                return jsonify({
                    "original": result.original_content,
                    "translated": result.translated_content,
                    "status": result.status.name,
                    "engine": result.engine,
                    "business_id": result.business_id,
                    "from_cache": result.from_cache,
                    "context_hash": result.context_hash
                })
            else:
                # 如果没有新任务被处理（可能已在缓存中），尝试从缓存查询（如果需要）
                # 注意：process_pending_translations 只有在有 PENDING 或 FAILED 任务时才返回结果
                # 如果是缓存命中，需要额外的 get_translation 方法
                cached_result = coordinator.handler.get_translation(text_content, target_lang, context)
                if cached_result:
                     return jsonify({
                        "original": cached_result.original_content,
                        "translated": cached_result.translated_content,
                        "status": cached_result.status.name,
                        "engine": cached_result.engine,
                        "business_id": cached_result.business_id,
                        "from_cache": cached_result.from_cache,
                        "context_hash": cached_result.context_hash
                    })
                else:
                    return jsonify({"message": "Translation task is pending or not found. Please check backend logs."}), 202

        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            log.error("翻译请求处理失败", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    if __name__ == '__main__':
        load_dotenv() # 在应用启动时加载 .env
        app.run(debug=True)
    ```

2.  **运行 Flask 应用**:
    ```bash
    python app.py
    ```

3.  **发送 POST 请求**:
    使用 `curl` 或 Postman 等工具发送 POST 请求到 `http://127.0.0.1:5000/translate`。

    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{
        "text": "Hello, Flask world!",
        "target_lang": "zh-CN",
        "business_id": "web_app.greeting.flask_hello"
    }' http://127.0.0.1:5000/translate
    ```
    **带上下文的例子**:
    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{
        "text": "Apple",
        "target_lang": "zh-CN",
        "business_id": "web_app.product.apple_fruit",
        "context": {"category": "fruit"}
    }' http://127.0.0.1:5000/translate
    ```

### **预期输出**

你会收到包含翻译结果的 JSON 响应，并看到相应的日志输出。第二次请求相同内容时，`from_cache` 字段会变为 `true`。

**重要考虑事项**：
*   在真实的生产 Web 应用中，`process_pending_translations` **不应该在请求处理线程中直接调用**。它通常作为一个独立的后台任务（例如使用 Celery, RQ 等消息队列）来周期性地执行，以避免阻塞 Web 请求。`translate_text` 接口只负责 `coordinator.request()` 登记任务。
*   `PersistenceHandler` 的数据库连接在 Web 应用中需要考虑连接池管理，以提高性能和稳定性。

## **10. 日志与可观测性：深入洞察**

`Trans-Hub` 使用 `structlog` 提供结构化日志，并支持 `correlation_id`，这对于调试和分析复杂系统至关重要。

### **目标**
利用 `structlog` 的强大功能进行调试和问题追踪。

### **步骤**

1.  **修改日志级别**:
    在 `logging_config.py` 或直接在 `initialize_trans_hub` 函数中，将日志级别从 `INFO` 调整为 `DEBUG` 或 `CRITICAL`，以查看更多或更少的细节。
    ```python
    # quick_start.py (initialize_trans_hub 部分修改)
    def initialize_trans_hub():
        setup_logging(log_level="DEBUG") # 将级别设置为 DEBUG
        # ...
    ```

2.  **理解结构化日志**:
    当你运行 `Trans-Hub` 时，日志默认以可读的控制台格式输出。但在生产环境中，结构化日志（JSON 格式）更便于日志聚合和分析工具处理。

    *   **启用 JSON 格式**: 你可以通过设置环境变量 `ENV=prod` 来切换到 JSON 格式。
        ```bash
        ENV=prod python quick_start.py
        ```
        或者在 `setup_logging` 中直接指定 `log_format="json"`。

    *   **示例 JSON 日志**:
        ```json
        {"event": "正在登记翻译任务", "text": "Hello, world!", "lang": "zh-CN", "logger": "__main__", "level": "info", "timestamp": "2025-06-13T16:00:00.000000Z", "correlation_id": "abc123def456"}
        ```

3.  **使用 `correlation_id` 进行追踪**:
    `Trans-Hub` 在内部使用 `structlog.contextvars` 来绑定 `correlation_id`。这意味着在同一个逻辑流中的所有日志行都会自动带上相同的 `correlation_id`。

    *   **设置 `correlation_id`**: 你可以在你的应用入口点手动设置 `correlation_id`，它将传播到 `Trans-Hub` 的所有内部日志中。
        ```python
        # app.py 或 main.py 的某个入口点
        import structlog.contextvars
        import uuid

        def main_entry_point():
            correlation_id = str(uuid.uuid4())
            structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
            # ... 调用 Trans-Hub 协调器 ...
        ```
    *   **日志过滤**: 当你在日志管理系统中（如 ELK Stack）查看日志时，你可以通过 `correlation_id` 轻松地过滤出特定请求或批次的所有相关日志，极大地简化问题排查。

---

希望这份 `Cookbook` 能帮助你更好地使用 `Trans-Hub`！如果你有任何新的“食谱”或改进建议，欢迎贡献！