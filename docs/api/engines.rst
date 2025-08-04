.. # docs/api/engines.rst

====================
翻译引擎 (Engines)
====================

本部分包含翻译引擎的基类以及所有内置的引擎实现。翻译引擎是 `Trans-Hub` 系统的核心组件，负责实际执行文本翻译操作。

引擎概述
--------

`Trans-Hub` 采用插件式引擎架构，支持多种不同的翻译引擎。您可以根据需求选择合适的引擎，或通过 :doc:`../guides/creating_an_engine` 指南来开发自定义引擎。

引擎基类
--------

所有翻译引擎都继承自 ``BaseTranslationEngine`` 基类，它定义了统一的接口和通用的批处理、并发与速率限制功能。

.. currentmodule:: trans_hub.engines.base

.. autoclass:: BaseTranslationEngine
   :members: initialize, close, validate_and_parse_context, atranslate_batch
   :undoc-members: false
   :show-inheritance:

.. autoclass:: BaseEngineConfig
   :members:

.. autoclass:: BaseContextModel
   :members:

内置引擎
--------

### Debug 引擎

一个用于开发和测试的调试引擎，它不进行实际的翻译调用。

.. currentmodule:: trans_hub.engines.debug
.. autoclass:: DebugEngine
.. autoclass:: DebugEngineConfig
   :members:
   :undoc-members:

### OpenAI 引擎

集成了 OpenAI 的翻译能力，特别适合需要高质量、支持上下文微调的翻译场景。

.. currentmodule:: trans_hub.engines.openai
.. autoclass:: OpenAIEngine
.. autoclass:: OpenAIEngineConfig
   :members:
   :undoc-members:
.. autoclass:: OpenAIContext
   :members:
   :undoc-members:

### Translators 引擎

一个通用的翻译引擎，底层使用 `translators` 库，支持多种免费在线翻译服务。

.. currentmodule:: trans_hub.engines.translators_engine
.. autoclass:: TranslatorsEngine
.. autoclass:: TranslatorsEngineConfig
   :members:
   :undoc-members:
.. autoclass:: TranslatorsContextModel
   :members:
   :undoc-members: