.. # docs/api/engines.rst

====================
翻译引擎 (Engines)
====================

本部分包含翻译引擎的基类以及所有内置的引擎实现。翻译引擎是 `Trans-Hub` 系统的核心组件，负责实际执行文本翻译操作。

引擎概述
--------

`Trans-Hub` 采用插件式引擎架构，支持多种不同的翻译引擎。您可以根据需求选择合适的引擎，或通过 :doc:`../guides/creating_an_engine` 指南来开发自定义引擎。

**引擎选择考虑因素**:

- 翻译质量
- 速度与成本
- 语言支持范围
- 特定功能需求（如上下文微调）

引擎基类
--------

所有翻译引擎都继承自 ``BaseTranslationEngine`` 基类，它定义了统一的接口和通用的批处理、并发与速率限制功能。

.. currentmodule:: trans_hub.engines.base

.. autoclass:: BaseTranslationEngine
   :members: initialize, close, validate_and_parse_context, atranslate_batch
   :undoc-members: false
   :show-inheritance:

.. autoclass:: BaseEngineConfig

.. autoclass:: BaseContextModel

内置引擎
--------

`Trans-Hub` 提供了多种内置翻译引擎，每种引擎都有其特定的优势和适用场景。

### Translators 引擎

一个通用的翻译引擎，底层使用 `translators` 库，支持多种免费在线翻译服务。

.. currentmodule:: trans_hub.engines.translators_engine
.. autoclass:: TranslatorsEngine
.. autoclass:: TranslatorsEngineConfig

.. rubric:: Translators 引擎特点

- 支持多种翻译服务（如 Google、Bing 等）
- 配置灵活，可随时切换底层服务
- 适合开发、测试或对翻译质量要求不高的场景

**使用示例**:

.. code-block:: shell
   :caption: .env 文件配置

   TH_ACTIVE_ENGINE="translators"
   # 可选：指定底层提供商
   TH_ENGINE_CONFIGS__TRANSLATORS__PROVIDER="bing"

### OpenAI 引擎

集成了 OpenAI 的翻译能力，特别适合需要高质量、支持上下文微调的翻译场景。

.. currentmodule:: trans_hub.engines.openai
.. autoclass:: OpenAIEngine
.. autoclass:: OpenAIEngineConfig
.. autoclass:: OpenAIContext

.. rubric:: OpenAI 引擎特点

- 翻译质量高，特别是对于复杂语境和专业术语
- 支持通过 :class:`OpenAIContext` 进行更准确的翻译
- 需要 OpenAI API 密钥

**使用示例**:

.. code-block:: shell
   :caption: .env 文件配置

   TH_ACTIVE_ENGINE="openai"
   TH_ENGINE_CONFIGS__OPENAI__OPENAI_API_KEY="sk-xxxxxxxxxx"
   TH_ENGINE_CONFIGS__OPENAI__OPENAI_MODEL="gpt-4o"

### Debug 引擎

一个用于开发和测试的调试引擎，它不进行实际的翻译调用。

.. currentmodule:: trans_hub.engines.debug
.. autoclass:: DebugEngine
.. autoclass:: DebugEngineConfig

.. rubric:: Debug 引擎特点

- 不进行实际翻译，仅返回预设结果
- 用于测试系统流程和错误处理
- 无需外部 API 密钥

**使用示例**:

.. code-block:: shell
   :caption: .env 文件配置

   TH_ACTIVE_ENGINE="debug"
   TH_ENGINE_CONFIGS__DEBUG__MODE="FAIL" # 模拟所有翻译都失败
   TH_ENGINE_CONFIGS__DEBUG__FAIL_IS_RETRYABLE="false" # 模拟不可重试的失败