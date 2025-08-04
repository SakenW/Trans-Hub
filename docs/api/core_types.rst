.. # docs/api/core_types.rst

.. currentmodule:: trans_hub.core.types

=================
核心类型 (Types)
=================

本文档是 `trans_hub.core.types` 模块中定义的所有核心数据传输对象（DTOs）的权威参考。这些 Pydantic 模型构成了 `Trans-Hub` 内部数据流的基础。

翻译状态枚举
------------

一个字符串枚举（`Enum`），表示翻译任务在数据库中的生命周期状态。

.. autoclass:: TranslationStatus
   :members:

引擎处理结果
------------

.. rubric:: EngineBatchItemResult

一个类型联合（`Union`），代表翻译引擎对单个文本的处理结果。它只能是 :class:`EngineSuccess` 或 :class:`EngineError` 之一。

表示单个文本翻译成功。`from_cache` 标志指示结果是否来自**翻译引擎自身**的内部缓存。
.. autoclass:: EngineSuccess
   :members:
   :show-inheritance:

表示单个文本翻译失败。`is_retryable` 是一个关键标志，`Coordinator` 将根据此标志决定是否对临时性错误进行重试。
.. autoclass:: EngineError
   :members:
   :show-inheritance:

内部翻译请求
------------

表示一个内部传递或用于缓存查找的翻译请求单元。
.. autoclass:: TranslationRequest
   :members:
   :show-inheritance:

最终翻译结果
------------

这是 `Coordinator` 返回给用户的最终结果对象。它聚合了来自数据库和翻译引擎的所有相关信息。
.. autoclass:: TranslationResult
   :members:
   :show-inheritance:
   
内部待办任务项
--------------

一个内部 DTO，代表 `Coordinator` 从 `PersistenceHandler` 获取的、待翻译的单个任务单元。
.. autoclass:: ContentItem
   :members:
   :show-inheritance:

全局上下文哨兵
----------------

一个特殊的字符串常量，当翻译请求没有提供上下文时，用作 `context_hash` 的值。
.. autoattribute:: GLOBAL_CONTEXT_SENTINEL