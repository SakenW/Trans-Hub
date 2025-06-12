# **Trans-Hub Cookbook: 实用范例与高级用法**

欢迎来到 `Trans-Hub` 的 Cookbook！这份文档将通过一系列实际的代码示例，向您展示如何充分利用 `Trans-Hub` 的各项功能，从基础设置到高级应用。

## 目录
1.  [基础：设置与第一个翻译请求](#1-基础设置与第一个翻译请求)
2.  [场景：在 Web 框架 (如 Flask) 中使用](#2-场景在-web-框架-如-flask-中使用)
3.  [场景：批量翻译数据文件 (如 CSV)](#3-场景批量翻译数据文件-如-csv)
4.  [高级用法：使用翻译上下文 (Context)](#4-高级用法使用翻译上下文-context)
5.  [高级用法：处理翻译结果与缓存状态](#5-高级用法处理翻译结果与缓存状态)
6.  [管理与维护：执行垃圾回收 (GC)](#6-管理与维护执行垃圾回收-gc)

---

### **1. 基础：设置与第一个翻译请求**

这个示例展示了初始化 `Trans-Hub` 并执行一次完整翻译流程的最基本步骤。它使用了 `Trans-Hub` 内置的、无需配置的免费翻译引擎。

```python
# basic_usage.py
import os
import structlog

# 导入 Trans-Hub 核心组件
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

log = structlog.get_logger()

def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    setup_logging(log_level="INFO")

    DB_FILE = "my_app_translations.db"
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    # 创建一个最简单的配置对象。
    # 它将自动使用默认的、免费的 'translators' 引擎。
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        engine_configs=EngineConfigs() # 使用默认的引擎配置
    )
    
    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

def main():
    coordinator = initialize_trans_hub()
    try:
        # 步骤 1: 登记翻译需求
        log.info("登记 'Hello, world!' 到日语和法语的翻译任务...")
        coordinator.request(
            target_langs=['ja', 'fr'], # 使用标准语言代码
            text_content="Hello, world!",
            business_id="app.greeting"
        )

        # 步骤 2: 在后台处理日语任务
        log.info("\n处理日语翻译...")
        jp_results = coordinator.process_pending_translations(target_lang='ja')
        for result in jp_results:
            log.info("实时结果", result=result.model_dump())

        # 步骤 3: 在另一个时间点处理法语任务
        log.info("\n处理法语翻译...")
        fr_results = coordinator.process_pending_translations(target_lang='fr')
        for result in fr_results:
            log.info("实时结果", result=result.model_dump())

    finally:
        coordinator.close()

if __name__ == "__main__":
    main()
```

### **2. 场景：在 Web 框架 (如 Flask) 中使用**

在 Web 应用中，`Coordinator` 实例应该在应用启动时被创建一次，并作为全局对象或应用上下文的一部分来复用，以避免重复创建数据库连接。

```python
# flask_app.py
from flask import Flask, jsonify
from dotenv import load_dotenv

from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.engines.openai import OpenAIEngineConfig
# ...其他导入...

# --- 应用级初始化 (只执行一次) ---
load_dotenv() # 加载 .env 文件

# 这里我们假设要使用 OpenAI 引擎
config = TransHubConfig(
    database_url="sqlite:///webapp.db",
    active_engine="openai",
    engine_configs=EngineConfigs(openai=OpenAIEngineConfig())
)
handler = DefaultPersistenceHandler(db_path="webapp.db")
apply_migrations("webapp.db")
# 全局的 Coordinator 实例
coordinator = Coordinator(config=config, persistence_handler=handler)

# --- Flask 应用 ---
app = Flask(__name__)

@app.route('/translate/<lang>/<path:text>')
def translate_text(lang, text):
    """一个简单的 API 端点，用于即席翻译。"""
    try:
        # 1. 登记即席翻译请求 (business_id=None)
        coordinator.request(target_langs=[lang], text_content=text, business_id=None)
        
        # 2. 立即处理并获取结果
        # 警告：在生产环境中，这应该由后台工作者（如 Celery）异步执行，避免阻塞Web请求。
        results = list(coordinator.process_pending_translations(target_lang=lang, limit=1))
        
        if results:
            return jsonify(results[0].model_dump())
        else:
            # 可能已在缓存中，需要一个 get_translation 方法来直接查询
            return jsonify({"status": "pending or cached"})
            
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
```

### **3. 场景：批量翻译数据文件 (如 CSV)**

`Trans-Hub` 的持久化缓存特性在这里能大放异彩，当 CSV 中有大量重复内容时，可以避免重复翻译。

```python
# process_csv.py
# ... (假设 coordinator 已经按照基础示例初始化好) ...

import csv

def process_csv(input_file: str, target_lang: str):
    # 步骤 1: 遍历 CSV，登记所有需要翻译的任务
    log.info(f"读取 {input_file} 并登记翻译任务...")
    texts_to_translate = set()
    with open(input_file, 'r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            texts_to_translate.add(row['product_description'])

    for text in texts_to_translate:
        # 对于批量数据，我们可以不使用 business_id，利用内容缓存
        coordinator.request(
            target_langs=[target_lang],
            text_content=text,
            business_id=None
        )
    log.info(f"共登记了 {len(texts_to_translate)} 个独立内容的翻译任务。")

    # 步骤 2: 一次性处理所有待办任务
    log.info(f"\n正在批量处理所有 {target_lang} 的翻译任务...")
    # 这里可以不关心返回的实时结果，因为我们最终会从数据库读取
    list(coordinator.process_pending_translations(target_lang=target_lang))
    log.info("批量处理完成！")

# ... (main 函数中调用 process_csv) ...
```

### **4. 高级用法：使用翻译上下文 (Context)**

假设对于“确认”这个词，在“删除”操作的对话框中，我们希望翻译得更强烈；而在普通表单中，只需翻译为 "OK"。`context` 参数可以完美解决这个问题。

```python
# context_example.py
# ... (假设 coordinator 已初始化) ...

# 场景A: 普通表单的确认按钮
coordinator.request(
    target_langs=['de'],
    text_content="Confirm",
    business_id="ui.form.submit_button",
    context=None # 无特定上下文
)

# 场景B: 删除警告对话框的确认按钮
delete_context = {
    "tone": "urgent",
    "ui_element": "destructive_action_button"
}
coordinator.request(
    target_langs=['de'],
    text_content="Confirm",
    business_id="ui.delete_dialog.confirm_button",
    context=delete_context
)

# 处理任务时，Coordinator 会为这两个任务生成不同的 context_hash。
# 即使它们的原文都是 "Confirm"，它们也会被作为两个独立的翻译任务处理，
# 从而得到不同的翻译结果并被分别缓存。
list(coordinator.process_pending_translations(target_lang='de'))
```

### **5. 高级用法：处理翻译结果与缓存状态**

`Coordinator.process_pending_translations` 返回的 `TranslationResult` 对象中的 `from_cache` 字段，可以告诉你这个结果是来自实时API调用还是本地缓存。

* **注意**: v1.0 的 `process_pending_translations` 总是处理 `PENDING` 或 `FAILED` 状态的任务，因此 `from_cache` 在此流程中通常为 `False`。直接查询缓存的功能（例如 `get_translation()`）是未来版本的一个重要扩展方向。

### **6. 管理与维护：执行垃圾回收 (GC)**

随着时间推移，旧的、不再使用的翻译（比如被重构掉的UI文本）会堆积在数据库中。定期运行垃圾回收是保持系统健康的好习惯。

```python
# maintenance.py
# ... (假设 coordinator 已初始化) ...

log.info("开始执行垃圾回收...")

# 步骤 1: Dry Run (演习)
# 先看看如果清理90天前的数据会发生什么，但不实际删除。
retention_days = 90
stats_dry = coordinator.run_garbage_collection(
    retention_days=retention_days,
    dry_run=True
)
log.info("Dry Run 统计结果", stats=stats_dry)

# 步骤 2: 实际执行
# 在确认无误后，执行真正的清理操作。
# (在真实脚本中，这里可能需要一个用户确认步骤)
log.info("正在执行真正的 GC...")
stats_real = coordinator.run_garbage_collection(
    retention_days=retention_days,
    dry_run=False
)
log.info("GC 执行完毕", stats=stats_real)

coordinator.close()
```
