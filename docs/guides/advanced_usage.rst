.. # docs/guides/advanced_usage.rst

================
高级用法指南
================

恭喜你完成了 :doc:`../getting_started`！本指南将带你探索 `Trans-Hub` 的高级功能，帮助你充分利用其强大的翻译与工作流能力。

引擎激活与运行时切换
----------------------

`Trans-Hub` 支持多种翻译引擎，你可以在配置时或运行时动态切换：

.. code-block:: python
   :caption: 方式1: 通过配置文件初始化

   from trans_hub import TransHubConfig
   config = TransHubConfig(active_engine="openai")
   # 也可以在 .env 文件中设置: TH_ACTIVE_ENGINE=openai

.. code-block:: python
   :caption: 方式2: 运行时切换

   # 假设 coordinator 已用默认引擎初始化
   coordinator.switch_engine("google")
   # 所有后续操作都将使用新的引擎

`business_id` 与 `context` 的区别与应用
---------------------------------------

这两个概念是 `Trans-Hub` 设计的核心，理解它们的区别至关重要。

`business_id`: 身份标识
^^^^^^^^^^^^^^^^^^^^^^^^

- 作用: 用于生命周期管理和来源追踪。例如，你可以通过 `business_id` 来更新或重新翻译某个特定的文本。
- 特点: 存储在独立的 `th_jobs` 表中，不影响翻译结果。
- 推荐命名: 带命名空间的点分式路径，如 ``ui.login-page.title``。

`context`: 翻译情境
^^^^^^^^^^^^^^^^^^^^

- 作用: 用于区分不同情境下的翻译，会直接影响翻译结果。
- 特点: 其哈希值是数据库中翻译记录唯一性约束的一部分。
- 使用场景: 当同一个文本在不同上下文中有不同翻译时必须使用。例如，单词 "Submit" 在软件界面中应翻译为“提交”，但在法律文件中可能需要翻译为“呈递”。

上下文翻译实战
--------------

### 基本上下文用法

在请求翻译时，通过一个简单的字典来提供上下文。

.. code-block:: python

   # 请求翻译时提供上下文
   await coordinator.request(
       text_content="Submit",
       target_langs=["zh-CN"],
       business_id="docs.legal.clause_1.submit_button",
       context={"domain": "legal", "tone": "formal"}
   )

### 自定义上下文模型

对于复杂的、结构化的上下文需求，最佳实践是定义自己的 Pydantic 模型，这能为您提供类型安全和自动验证。

.. code-block:: python

   from trans_hub.engines.base import BaseContextModel
   from pydantic import Field

   class MyAppContext(BaseContextModel):
       domain: str = Field(description="翻译领域，如 'medical', 'legal'")
       tone: str = Field(default="neutral", description="语气")
       audience: str = Field(default="general", description="目标受众")

   # 使用自定义上下文模型
   my_context = MyAppContext(domain="medical", tone="professional")
   
   await coordinator.request(
       text_content="冠心病",
       target_langs=["en"],
       business_id="app.medical_term.001",
       context=my_context.model_dump() # 传递字典
   )

并发控制与缓存策略
--------------------

`Trans-Hub` 的性能和成本很大程度上取决于并发与缓存配置。

### 并发控制

你可以在引擎配置中调整其独有的并发控制参数。

.. code-block:: python
   :caption: 在 TransHubConfig 中配置 OpenAI 引擎的并发

   # config = TransHubConfig(
   #     engine_configs={
   #         "openai": {
   #             "rpm": 3000, # 每分钟最多3000次请求
   #             "max_concurrency": 10 # 最大并发请求数为10
   #         }
   #     }
   # )
   # 注意: 这是一个示例，实际配置应通过 pydantic-settings 加载

### 缓存策略

缓存由 `Coordinator` 统一管理。

- **禁用缓存**: 在 `request` 时通过 `force_retranslate=True` 标志来强制重新翻译，绕过所有缓存。

  .. code-block:: python

     await coordinator.request(
         text_content="这是一个需要立即更新的动态内容",
         target_langs=["en"],
         force_retranslate=True # 强制重新翻译
     )

- **配置缓存**: 在全局配置中调整内存缓存的 TTL (存活时间) 和大小。

  .. code-block:: python

     # config = TransHubConfig(
     #     cache_config={
     #         "ttl": 3600,  # 缓存有效期（秒）
     #         "maxsize": 10000  # 内存缓存项数限制
     #     }
     # )

错误处理与重试机制
--------------------

### 自定义错误处理

`Trans-Hub` 定义了一系列语义化的异常，方便您进行精确的错误处理。

.. code-block:: python

   from trans_hub.exceptions import TransHubError, EngineError, DatabaseError

   try:
       # ... 执行 coordinator 的某个方法 ...
       pass
   except TransHubError as e:
       if isinstance(e, EngineError):
           print(f"引擎 API 错误: {e}")
       elif isinstance(e, DatabaseError):
           print(f"数据库错误: {e}")
       else:
           print(f"未知的 Trans-Hub 错误: {e}")

### 重试策略配置

在全局配置中调整后台 Worker 的重试策略。

.. code-block:: python

   # config = TransHubConfig(
   #     retry_policy={
   #         "max_attempts": 3,  # 最大尝试次数 (首次 + 2次重试)
   #         "initial_backoff": 2.0  # 初始退避时间（秒），后续指数增长
   #     }
   # )

与 Web 框架集成 (FastAPI)
----------------------------

`Trans-Hub` 的纯异步设计使其能与 FastAPI 等现代 Web 框架无缝集成。推荐使用 FastAPI 的依赖注入系统来管理 `Coordinator` 的生命周期。

.. code-block:: python
   :caption: main.py - FastAPI 集成示例

   from fastapi import FastAPI, Depends
   from contextlib import asynccontextmanager
   from trans_hub import Coordinator, TransHubConfig
   from trans_hub.persistence import create_persistence_handler

   # 使用 FastAPI 的生命周期事件来管理 Coordinator 实例
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # 应用启动时
       config = TransHubConfig()
       handler = create_persistence_handler(config)
       coordinator = Coordinator(config, handler)
       await coordinator.initialize()
       app.state.coordinator = coordinator
       yield
       # 应用关闭时
       await app.state.coordinator.close()

   app = FastAPI(lifespan=lifespan)

   def get_coordinator(request) -> Coordinator:
       return request.app.state.coordinator

   @app.post("/translate/")
   async def submit_translation_request(
       text: str,
       target_lang: str,
       coordinator: Coordinator = Depends(get_coordinator)
   ):
       # 提交一个后台翻译任务，并立即返回
       await coordinator.request(
           text_content=text,
           target_langs=[target_lang],
       )
       return {"message": "Translation request received and is being processed."}

下一步
------

- 了解如何 :doc:`配置 Trans-Hub <../configuration>` 的更多参数。
- 学习 :doc:`部署 <deployment>` 最佳实践。
- 探索 :doc:`命令行工具 <../cli_reference>` 的使用。