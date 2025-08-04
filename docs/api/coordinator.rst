.. # docs/api/coordinator.rst

.. currentmodule:: trans_hub.coordinator

=====================
协调器 (Coordinator)
=====================

`Coordinator` 是 `Trans-Hub` 的核心编排器，是您与系统交互的主要入口点。它是一个**纯异步**的类，负责管理从任务登记到最终获取结果的整个翻译生命周期。

核心职责
--------

- **接收翻译请求**: 通过 `request()` 方法，使用稳定的业务 ID (`business_id`) 和结构化载荷 (`payload`) 快速登记任务。
- **后台处理**: 在独立的后台工作进程中，通过 `process_pending_translations()` 流式处理待办任务。
- **引擎管理**: 管理并调用当前活动的翻译引擎，支持运行时切换。
- **策略应用**: 自动应用重试和速率限制策略。
- **结果查询**: 通过 `get_translation()` 高效查询已完成的翻译结果。

核心工作模式：两阶段分离
------------------------

`Trans-Hub` 的设计精髓在于将**任务登记**和**任务处理**两个阶段完全分离。

1.  **阶段一：请求登记 (Request Phase)**
    您的主应用调用 `await coordinator.request(...)`。这个方法非常快，因为它只在数据库中创建或更新记录，然后立即返回。

2.  **阶段二：后台处理 (Processing Phase)**
    一个或多个独立的后台工作进程（Worker）持续地调用 `async for result in coordinator.process_pending_translations(...)` 来处理任务。

这种分离确保了您的主应用线程不会被耗时较长的翻译 API 调用所阻塞。

.. _coordinator-api-reference:

API 参考
========

.. autoclass:: Coordinator
   :members: __init__, initialize, close, switch_engine, request, process_pending_translations, get_translation, run_garbage_collection
   :undoc-members: false
   :show-inheritance:
   :member-order: bysource

   .. rubric:: __init__ 方法说明

   `Coordinator` 的构造函数是一个同步方法，负责注入所有依赖项。**此方法不执行任何 I/O 操作。**

   .. rubric:: 缓存策略说明

   在 v3.0 架构中，`Coordinator` 的职责更加清晰。
   - `get_translation()` 方法现在专注于与**持久化层**交互，获取已存储的结果。
   - **内存缓存**的主要作用体现在后台处理流程 (`ProcessingPolicy`) 中，用于避免在单个 Worker 的生命周期内对完全相同的任务（原文、语言、上下文）进行重复的 API 调用，从而节省成本和时间。