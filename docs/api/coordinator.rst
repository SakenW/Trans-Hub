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
   :members: __init__, initialize, close, switch_engine, request, process_pending_translations, get_translation, run_garbage_collection, touch_jobs
   :undoc-members: false
   :show-inheritance:
   :member-order: bysource

   .. rubric:: __init__ 方法说明

   `Coordinator` 的构造函数是一个同步方法，负责注入所有依赖项。**此方法不执行任何 I/O 操作。** 创建的实例可以在您的应用中安全地复用。

   .. rubric:: 两级缓存查询策略

   `get_translation()` 方法实现了一个高效的两级缓存查询策略：

   1.  **L1 缓存**: 首先检查高速的**内存缓存** (使用 `cachetools`)。
   2.  **L2 缓存**: 如果内存缓存未命中，则查询**持久化存储** (数据库)。
   3.  **回填机制**: 如果从数据库中找到结果，它会自动将其**回填**到内存缓存中，以加速后续对相同内容的查询。