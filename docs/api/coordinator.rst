.. # docs/api/coordinator.rst

.. currentmodule:: trans_hub.coordinator

=====================
协调器 (Coordinator)
=====================

`Coordinator` 是 `Trans-Hub` 的核心编排器，是您与系统交互的主要入口点。它是一个**纯异步**的类，负责管理从任务登记到最终获取结果的整个翻译生命周期。

核心职责
--------

- **接收翻译请求**: 通过轻量级的 `request()` 方法快速登记任务。
- **后台处理**: 在独立的后台工作进程中，通过 `process_pending_translations()` 流式处理待办任务。
- **引擎调用**: 管理并调用当前活动的翻译引擎。
- **策略应用**: 自动应用缓存（内存缓存 + 持久化层）、重试和速率限制策略。
- **结果查询**: 通过 `get_translation()` 高效查询已完成的翻译结果。

核心工作模式：两阶段分离
------------------------

`Trans-Hub` 的设计精髓在于将**任务登记**和**任务处理**两个阶段完全分离，这使得它非常适合高并发的 Web 服务或需要后台处理大量文本的应用。

1.  **阶段一：请求登记 (Request Phase)**
    您的主应用（例如一个 FastAPI 端点）调用 `await coordinator.request(...)`。这个方法非常快，因为它只在数据库中创建或更新一条记录，然后立即返回。

2.  **阶段二：后台处理 (Processing Phase)**
    一个或多个独立的后台工作进程（Worker）持续地调用 `async for result in coordinator.process_pending_translations(...)`。这个异步生成器会不断地从数据库中拉取待办任务，通过翻译引擎处理它们，然后将结果存回数据库。

这种分离确保了您的主应用线程不会被耗时较长的翻译 API 调用所阻塞。

.. _coordinator-api-reference:

API 参考
========

.. autoclass:: Coordinator
   :members:
   :undoc-members: false
   :show-inheritance:
   :member-order: bysource
   :exclude-members: run_migrations, run_garbage_collection, touch_jobs

   .. rubric:: __init__ 方法说明

   `Coordinator` 的构造函数是一个同步方法，负责注入所有依赖项。**此方法不执行任何 I/O 操作。** 创建的实例可以在您的应用中安全地复用。

   .. rubric:: 两级缓存查询策略

   `get_translation()` 方法实现了一个高效的两级缓存查询策略：

   1.  **L1 缓存**: 首先检查高速的**内存缓存** (使用 `cachetools`)。
   2.  **L2 缓存**: 如果内存缓存未命中，则查询**持久化存储** (数据库)。
   3.  **回填机制**: 如果从数据库中找到结果，它会自动将其**回填**到内存缓存中，以加速后续对相同内容的查询。

完整使用示例
============

下面的示例展示了一个典型的“请求-处理-查询”完整生命周期。

.. code-block:: python
   :caption: main.py - 模拟应用主逻辑和后台 Worker

   import asyncio
   from trans_hub import Coordinator, TransHubConfig, TranslationStatus
   from trans_hub.persistence import create_persistence_handler
   from trans_hub.db.schema_manager import apply_migrations

   async def main():
       # 1. 初始化
       print("--- 1. 初始化组件 ---")
       config = TransHubConfig(database_url="sqlite:///./test_doc_usage.db")
       apply_migrations(config.db_path) # 确保数据库 Schema 是最新的
       
       handler = create_persistence_handler(config)
       coordinator = Coordinator(config, handler)
       await coordinator.initialize()

       # 2. 客户端发起翻译请求 (快速完成)
       print("\n--- 2. 登记翻译任务 ---")
       text_to_translate = "Hello, world!"
       await coordinator.request(
           text_content=text_to_translate,
           target_langs=["zh-CN", "ja", "fr"],
           business_id="doc-example-001"
       )
       print(f"✅ 任务 '{text_to_translate}' 已成功登记。")

       # 3. 后台 Worker 处理中文翻译任务
       print("\n--- 3. 后台 Worker 开始处理中文任务 ---")
       async for result in coordinator.process_pending_translations("zh-CN"):
           if result.status == TranslationStatus.TRANSLATED:
               print(f"  - 翻译成功: '{result.original_content}' -> '{result.translated_content}'")
           else:
               print(f"  - 翻译失败: '{result.original_content}', 错误: {result.error}")
       print("✅ 中文任务处理完成。")
       
       # 4. 客户端查询已完成的翻译
       print("\n--- 4. 客户端查询结果 ---")
       # 第一次查询 (可能走数据库)
       zh_result = await coordinator.get_translation(text_to_translate, "zh-CN")
       if zh_result:
           print(f"  - 查询到中文翻译: {zh_result.translated_content}")

       # 第二次查询 (大概率走内存缓存)
       zh_result_cached = await coordinator.get_translation(text_to_translate, "zh-CN")
       if zh_result_cached:
           print(f"  - 再次查询到中文翻译 (可能来自缓存): {zh_result_cached.translated_content}")

       # 查询一个尚未被处理的语言
       fr_result = await coordinator.get_translation(text_to_translate, "fr")
       print(f"  - 查询法文翻译结果: {fr_result}") # 预期为 None

       # 5. 清理
       await coordinator.close()
       # 在实际应用中，您可能需要手动清理数据库文件
       # import os; os.remove(config.db_path)

   if __name__ == "__main__":
       asyncio.run(main())