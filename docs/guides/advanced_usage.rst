.. # docs/guides/advanced_usage.rst

================
高级用法指南
================

本指南将带你探索 `Trans-Hub v3.0` 的高级功能。

稳定引用ID (`business_id`)
---------------------------------

在 v3.0 中, `business_id` 是定位一个内容的**唯一稳定标识**。它与原文（`source_payload`）解耦，允许您在不改变 `business_id` 的情况下更新原文。

- **作用**: 保证了即使原文内容变化，您应用代码中的引用 (`business_id`) 仍然有效。
- **推荐命名**: 带命名空间的点分式路径，如 ``ui.login-page.title``。

结构化载荷 (`payload`)
-----------------------

`Trans-Hub` 现在原生支持 JSON 格式的结构化内容。

- **约定**: `payload` 字典中**必须**包含一个 `"text"` 键，用于存放需要被翻译的核心文本。
- **优势**: 您可以在 `payload` 中携带任何不需翻译的元数据（如 `max_length`, `style`），这些元数据会在翻译流程中被完整保留。

.. code-block:: python
   :caption: 提交一个带元数据的 payload

   await coordinator.request(
       business_id="ui.buttons.confirm",
       source_payload={
           "text": "Confirm",
           "style": "primary",
           "icon": "check_circle"
       },
       target_langs=["de"]
   )

   # 获取到的 translated_payload 将会是：
   # {
   #    "text": "Bestätigen",
   #    "style": "primary",
   #    "icon": "check_circle"
   # }

上下文翻译 (`context`)
-----------------------

`context` 用于区分**同一个 `business_id` 和 `source_payload` 在不同情境下的翻译**。

.. code-block:: python
   :caption: 为同一个按钮请求不同上下文的翻译

   # 网页版按钮
   await coordinator.request(
       business_id="ui.buttons.submit",
       source_payload={"text": "Submit"},
       target_langs=["de"],
       context={"platform": "web"}
   )

   # 移动版按钮，可能需要更短的文本
   await coordinator.request(
       business_id="ui.buttons.submit",
       source_payload={"text": "Submit"},
       target_langs=["de"],
       context={"platform": "mobile"}
   )

   # 获取时也需要提供 context
   web_translation = await coordinator.get_translation(
       business_id="ui.buttons.submit",
       target_lang="de",
       context={"platform": "web"}
   )

与 Web 框架集成 (FastAPI)
----------------------------

`Trans-Hub` 的纯异步设计使其能与 FastAPI 等现代 Web 框架无缝集成。

.. code-block:: python
   :caption: main.py - FastAPI 集成示例

   from fastapi import FastAPI, Depends, Request
   from contextlib import asynccontextmanager
   from trans_hub import Coordinator, TransHubConfig
   from trans_hub.persistence import create_persistence_handler

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

   def get_coordinator(request: Request) -> Coordinator:
       return request.app.state.coordinator

   @app.post("/translate/")
   async def submit_translation_request(
       business_id: str,
       text: str,
       target_lang: str,
       coordinator: Coordinator = Depends(get_coordinator)
   ):
       await coordinator.request(
           business_id=business_id,
           source_payload={"text": text},
           target_langs=[target_lang],
       )
       return {"message": "Translation request received."}