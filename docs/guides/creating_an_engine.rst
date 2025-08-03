.. # docs/guides/creating_an_engine.rst

=====================================
为 Trans-Hub 开发新引擎
=====================================

欢迎你，未来的贡献者！本指南将带你一步步地为 `Trans-Hub` 开发一个全新的翻译引擎。得益于 `Trans-Hub` 的纯异步、动态发现的架构，这个过程比你想象的要简单得多。

在开始之前，我们假设你已经对 `Trans-Hub` 的 :doc:`核心架构 <architecture>` 有了基本的了解。

开发哲学：引擎的职责
--------------------

在 `Trans-Hub` 的架构中，一个 `Engine` 的职责被严格限定在：

- 实现一个 ``async def _execute_single_translation(...)`` 方法。
- 接收**一个**字符串、目标语言等参数。
- 与一个特定的外部翻译 API 进行通信。
- 将 API 的成功或失败结果，包装成 ``EngineSuccess`` 或 ``EngineError`` 对象并 ``return``。

引擎**不需要**关心：

- **批处理和并发**: ``BaseTranslationEngine`` 会自动处理。
- **数据库、缓存、重试、速率限制**: 这些都由 ``Coordinator`` 处理。

核心模式：只实现 `_execute_single_translation`
--------------------------------------------------------------------

这是为 `Trans-Hub` 开发引擎的**唯一核心要求**。你的引擎主类必须继承 ``BaseTranslationEngine``，但你**唯一**需要重写的方法就是 ``_execute_single_translation``。基类已经为你处理了所有外围的批处理和控制逻辑。

开发流程：两步完成
--------------------

假设我们要创建一个对接 “Awesome Translate” 服务的引擎。

第一步：创建引擎文件
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

在 ``trans_hub/engines/`` 目录下，创建一个新的 Python 文件，例如 **`awesome_engine.py`**。

第二步：实现引擎代码
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

打开 ``awesome_engine.py`` 文件，并遵循以下结构编写代码。这是构建一个新引擎的“黄金模板”。

1.  **导入**: 导入所有必要的模块，包括 ``BaseTranslationEngine``。
2.  **定义配置模型 (`...Config`)**: 创建一个继承自 ``BaseEngineConfig`` 的 Pydantic 模型。
3.  **定义引擎主类 (`...Engine`)**: 创建一个继承自 ``BaseTranslationEngine`` 的主类，并实现 ``_execute_single_translation`` 方法。

第三步：完成
^^^^^^^^^^^^

完成了！你**不需要**再修改任何其他文件。

:class:`~trans_hub.coordinator.Coordinator` 在初始化时会自动触发引擎发现逻辑。当您的应用实例化 `Coordinator` 时，它就会扫描 `engines` 目录并自动加载、注册您的新引擎。

当用户在 :class:`~trans_hub.config.TransHubConfig` 中设置 ``active_engine="awesome"`` 时，整个系统会自动协同工作。

异步适配：处理同步库
--------------------

- **如果你的目标 API 提供了 ``asyncio`` 客户端** (例如 `openai` 库)，请直接在 ``_execute_single_translation`` 中使用 ``await`` 调用它。
- **如果你的目标 API 只有一个同步的、阻塞的库** (例如 `translators` 库)，你**必须**使用 ``asyncio.to_thread`` 来包装这个阻塞调用，以避免阻塞主事件循环。

这是适配同步库的“黄金范例”：

.. code-block:: python

   # awesome_engine.py (假设 awesome_sdk 是同步的)
   import asyncio
   from trans_hub.engines.base import BaseTranslationEngine
   # ...

   class AwesomeEngine(BaseTranslationEngine[...]):
       # ...

       def _translate_sync(self, text: str) -> EngineBatchItemResult:
           """[私有] 这是一个执行阻塞操作的同步方法。"""
           # ... 同步的 API 调用逻辑 ...

       async def _execute_single_translation(self, text: str, ...) -> EngineBatchItemResult:
           """[实现] 这是必须实现的异步接口。"""
           # 使用 asyncio.to_thread 将同步方法包装成一个可等待对象
           return await asyncio.to_thread(self._translate_sync, text)

进阶技巧：支持自定义上下文
--------------------------

要让你的引擎能够利用在翻译请求中传递的 ``context`` 字典，你需要：

1.  **定义一个 `ContextModel`**: 在你的引擎文件中，创建一个继承自 ``BaseContextModel`` 的 Pydantic 模型，并定义你希望从 `context` 中接收的字段。

    .. code-block:: python
       :caption: awesome_engine.py

       from trans_hub.engines.base import BaseContextModel

       class AwesomeEngineContext(BaseContextModel):
           # 允许用户通过 context={"tone": "formal"} 来指定语气
           tone: Optional[str] = None

2.  **在 ``_execute_single_translation`` 中使用 ``context_config``**: 基类会自动验证 ``context`` 并将结果以字典形式传入 ``context_config`` 参数。

    .. code-block:: python
       :caption: awesome_engine.py
    
       class AwesomeEngine(BaseTranslationEngine[...]):
           # 别忘了在类属性中注册你的 Context 模型
           CONTEXT_MODEL = AwesomeEngineContext
           ACCEPTS_CONTEXT = True # 明确声明接受上下文
           
           async def _execute_single_translation(self, ..., context_config: dict[str, Any]) -> ...:
               tone = context_config.get("tone", "neutral") # 从上下文中获取 'tone'
               
               # 在你的 API 调用中使用 tone
               translated_text = await self.client.translate(..., tone=tone)
               # ...

一份完整的示例：`AwesomeEngine`
------------------------------------------

下面是一个完整的、遵循所有最佳实践的 ``awesome_engine.py`` 文件示例。

.. code-block:: python
   :caption: trans_hub/engines/awesome_engine.py (完整示例)
   :emphasize-lines: 12, 26

   import asyncio
   from typing import Any, Optional

   from trans_hub.engines.base import (
       BaseContextModel,
       BaseEngineConfig,
       BaseTranslationEngine,
   )
   from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

   # 假设有一个名为 'awesome_sdk' 的同步第三方库
   try:
       import awesome_sdk
   except ImportError:
       awesome_sdk = None

   # --- 1. 定义配置模型 ---
   class AwesomeEngineConfig(BaseEngineConfig):
       # pydantic-settings 会自动从 .env 和环境变量加载
       # (需以 TH_ENGINE_CONFIGS__AWESOME__... 为前缀)
       awesome_api_key: str

   # --- 2. 定义引擎主类 ---
   class AwesomeEngine(BaseTranslationEngine[AwesomeEngineConfig]):
       CONFIG_MODEL = AwesomeEngineConfig
       VERSION = "1.0.0"

       def __init__(self, config: AwesomeEngineConfig):
           super().__init__(config)
           if awesome_sdk is None:
               raise ImportError("要使用 AwesomeEngine，请先安装 'awesome-sdk' 库")
           self.client = awesome_sdk.Client(api_key=config.awesome_api_key)

       def _translate_sync(self, text: str, target_lang: str) -> EngineBatchItemResult:
           """[私有] 这是一个执行阻塞 I/O 的同步方法。"""
           try:
               translated_text = self.client.translate(
                   text=text, target_language=target_lang
               )
               return EngineSuccess(translated_text=translated_text)
           except awesome_sdk.AuthError as e:
               return EngineError(error_message=f"认证错误: {e}", is_retryable=False)
           except Exception as e:
               return EngineError(error_message=f"未知错误: {e}", is_retryable=True)

       async def _execute_single_translation(
           self,
           text: str,
           target_lang: str,
           source_lang: Optional[str],
           context_config: dict[str, Any],
       ) -> EngineBatchItemResult:
           """[实现] 通过 asyncio.to_thread 包装同步调用。"""
           return await asyncio.to_thread(self._translate_sync, text, target_lang)