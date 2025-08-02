.. # docs/api/engines.rst

翻译引擎 (Engines)
====================

本部分包含翻译引擎的基类以及所有内置的引擎实现。

引擎基类
--------
.. automodule:: trans_hub.engines.base
   :members: BaseTranslationEngine, BaseEngineConfig, BaseContextModel
   :undoc-members: false
   :show-inheritance:

内置引擎
--------

.. automodule:: trans_hub.engines.translators_engine
   :members: TranslatorsEngine, TranslatorsEngineConfig
   :undoc-members: false
   :show-inheritance:

.. automodule:: trans_hub.engines.openai
   :members: OpenAIEngine, OpenAIEngineConfig, OpenAIContext
   :undoc-members: false
   :show-inheritance:

.. automodule:: trans_hub.engines.debug
   :members: DebugEngine, DebugEngineConfig
   :undoc-members: false
   :show-inheritance: