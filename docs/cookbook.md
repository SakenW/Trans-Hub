# Trans-Hub Cookbook: 实用范例与高级用法

欢迎来到 `Trans-Hub` 的 Cookbook！这份文档将通过一系列实际的代码示例，向您展示如何充分利用 `Trans-Hub` 的各项功能。

## 目录
1.  [基础：设置与第一个翻译请求](#1-基础设置与第一个翻译请求)
2.  [场景：在 Web 框架 (如 Flask) 中使用](#2-场景在-web-框架-如-flask-中使用)
3.  [场景：批量处理数据文件](#3-场景批量处理数据文件)
4.  [高级用法：使用翻译上下文 (Context)](#4-高级用法使用翻译上下文-context)
5.  [高级用法：处理翻译结果与缓存](#5-高级用法处理翻译结果与缓存)
6.  [管理与维护：执行垃圾回收 (GC)](#6-管理与维护执行垃圾回收-gc)

---

### **1. 基础：设置与第一个翻译请求**

这个示例展示了初始化 `Trans-Hub` 并执行一次完整翻译流程的最基本步骤。

```python
import os
from dotenv import load_dotenv

# 导入 Trans-Hub 核心组件
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.openai import OpenAIEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    load_dotenv()
    setup_logging()

    DB_FILE = "production.db"
    if not os.path.exists(DB_FILE):
        print(f"正在创建数据库: {DB_FILE}")
        apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 从 .env 加载配置并构建总配置对象
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        active_engine="openai",
        engine_configs=EngineConfigs(
            openai=OpenAIEngineConfig()
        )
    )
    
    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

def main():
    coordinator = initialize_trans_hub()

    try:
        # 步骤 1: 登记翻译需求
        print("登记 'Hello' 到日语和法语的翻译任务...")
        coordinator.request(
            target_langs=['Japanese', 'French'],
            text_content="Hello, world!",
            business_id="app.greeting"
        )

        # 步骤 2: 在后台处理日语任务
        print("\n处理日语翻译...")
        jp_results = coordinator.process_pending_translations(target_lang='Japanese')
        for result in jp_results:
            print(f"  -> 实时结果: {result.original_content} -> {result.translated_content}")

        # 步骤 3: 在另一个时间点处理法语任务
        print("\n处理法语翻译...")
        fr_results = coordinator.process_pending_translations(target_lang='French')
        for result in fr_results:
            print(f"  -> 实时结果: {result.original_content} -> {result.translated_content}")

    finally:
        coordinator.close()

if __name__ == "__main__":
    main()
```

### **2. 场景：在 Web 框架 (如 Flask) 中使用**

在 Web 应用中，`Coordinator` 实例应该在应用启动时被创建一次，并作为全局对象或应用上下文的一部分来复用，以避免重复创建数据库连接。

```python
# app.py (一个简单的 Flask 应用示例)
from flask import Flask, g, jsonify
from dotenv import load_dotenv

from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
# ...其他导入...

# --- 初始化 Trans-Hub ---
# 在应用启动时只执行一次
load_dotenv()
DB_FILE = "webapp.db"
apply_migrations(DB_FILE)
handler = DefaultPersistenceHandler(db_path=DB_FILE)
config = TransHubConfig(
    database_url=f"sqlite:///{DB_FILE}",
    active_engine="openai",
    engine_configs=EngineConfigs(openai=OpenAIEngineConfig())
)
# 全局的 Coordinator 实例
coordinator = Coordinator(config=config, persistence_handler=handler)

# --- Flask 应用 ---
app = Flask(__name__)

@app.route('/translate/<lang>/<text>')
def translate_text(lang, text):
    """一个简单的 API 端点，用于即席翻译。"""
    
    # 1. 登记即席翻译请求 (business_id=None)
    coordinator.request(
        target_langs=[lang],
        text_content=text,
        business_id=None 
    )
    
    # 2. 立即处理这个任务并获取结果
    # 注意：在真实的 Web 应用中，重量级的 process_pending_translations
    # 应该由一个后台工作者（如 Celery）来异步执行，避免阻塞请求。
    # 这里为了演示，我们直接同步执行。
    results = list(coordinator.process_pending_translations(target_lang=lang, limit=1))
    
    if results:
        return jsonify(results[0].model_dump())
    else:
        return jsonify({"error": "Translation failed or no pending task found."}), 500

if __name__ == '__main__':
    app.run(debug=True)
```

### **3. 场景：批量处理数据文件**

假设你需要翻译一个 CSV 文件中的某一列。`Trans-Hub` 的持久化缓存特性在这里能大放异彩，避免重复翻译相同的内容。

```python
# process_data.py
import csv
import time

# 假设 coordinator 已经按照基础示例初始化好了
# coordinator = initialize_trans_hub() 

def process_csv(input_file: str, output_file: str, target_lang: str):
    
    # 步骤 1: 遍历 CSV，登记所有需要翻译的任务
    print(f"正在读取 {input_file} 并登记翻译任务...")
    with open(input_file, 'r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            text_to_translate = row['product_description']
            # 使用 表名+ID+字段名 作为唯一的 business_id
            business_id = f"products.{row['id']}.description"
            coordinator.request(
                target_langs=[target_lang],
                text_content=text_to_translate,
                business_id=business_id
            )
    print("所有任务登记完成！")

    # 步骤 2: 一次性处理所有待办任务
    print(f"\n正在批量处理所有 {target_lang} 的翻译任务...")
    # 这里可以不关心返回的实时结果，因为我们最终会从数据库读取
    list(coordinator.process_pending_translations(target_lang=target_lang))
    print("批量处理完成！")
    
    # 步骤 3: （可选）从数据库中直接获取所有已翻译的结果
    # 这是一个高级用法，实际应用中你可能需要为 PersistenceHandler 增加一个
    # `get_translation_by_business_id` 的方法来实现。
    # 这里我们只演示处理流程。
    
# main:
# coordinator = initialize_trans_hub()
# process_csv('products.csv', 'products_translated.csv', 'German')
# coordinator.close()
```

### **4. 高级用法：使用翻译上下文 (Context)**

假设对于“确认”这个词，在“删除”操作的对话框中，我们希望翻译得更强烈（如 "Confirm Deletion!"）；而在普通表单中，只需翻译为 "OK"。`context` 参数可以完美解决这个问题。

```python
# context_example.py

# ... 初始化 coordinator ...

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

# 处理任务时，Coordinator 会为这两个任务生成不同的 context_hash，
# 即使它们的原文都是 "Confirm"，它们也会被作为两个独立的翻译任务处理，
# 从而得到不同的翻译结果并被分别缓存。
list(coordinator.process_pending_translations(target_lang='de'))
```

### **5. 高级用法：处理翻译结果与缓存**

`Coordinator.process_pending_translations` 返回的是一个生成器，你可以实时地对结果进行处理。返回的 `TranslationResult` 对象中的 `from_cache` 字段可以告诉你这个结果是来自实时API调用还是本地缓存。

```python
# cache_handling_example.py

# ... 初始化 coordinator ...

# 第一次请求
coordinator.request(target_langs=['es'], text_content="cache test")
print("处理第一次请求...")
results1 = list(coordinator.process_pending_translations(target_lang='es'))
print(f"  -> 第一次结果: from_cache={results1[0].from_cache}") # 应该是 False

# 第二次处理同样的任务（假设没有新的请求）
# stream_translatable_items 不会返回任何内容，因为状态已经是 TRANSLATED
print("\n第二次处理，不应有任何输出...")
results2 = list(coordinator.process_pending_translations(target_lang='es'))
assert len(results2) == 0

# 如果需要强制重新翻译，你需要先在数据库层面将状态改回 PENDING，
# 或者实现一个带 'force_refresh' 标志的 request 方法（v2.0 功能）。

# 如果是另一个业务位置请求了相同的内容，它将从缓存中受益。
# 你需要一个 get_translation() 方法来直接查询缓存，
# 这是 Coordinator 未来可以增加的功能。
```

### **6. 管理与维护：执行垃圾回收 (GC)**

随着时间推移，旧的、不再使用的翻译（比如被重构掉的UI文本）会堆积在数据库中。定期运行垃圾回收是保持系统健康的好习惯。

```python
# maintenance.py (一个可以加入定时任务的脚本)

# ... 初始化 coordinator ...

print("开始执行垃圾回收...")

# 步骤 1: Dry Run (演习)
# 先看看如果清理90天前的数据会发生什么，但不实际删除。
retention_days = 90
stats_dry = coordinator.run_garbage_collection(
    retention_days=retention_days,
    dry_run=True
)
print(f"\n[Dry Run] 准备删除的统计信息: {stats_dry}")

# 步骤 2: 实际执行
# 在确认无误后，执行真正的清理操作。
# if user_confirms("你确定要删除吗?"):
stats_real = coordinator.run_garbage_collection(
    retention_days=retention_days,
    dry_run=False
)
print(f"\n[执行] 已清理的统计信息: {stats_real}")

coordinator.close()
```

---

这份 Cookbook 为用户提供了从入门到进阶的清晰路径。下一步，我们可以继续完善《第三方引擎开发指南》，让我们的生态系统更加开放和完整。