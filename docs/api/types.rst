.. # docs/api/types.rst

.. currentmodule:: trans_hub.types

==============
核心类型定义
==============

本文档是 `trans_hub.types` 模块中定义的所有核心数据传输对象（DTOs）的权威参考。这些 Pydantic 模型构成了 `Trans-Hub` 内部数据流的基础。

翻译状态枚举
------------

.. autoclass:: TranslationStatus
   :members:
   :undoc-members: false

   一个字符串枚举（`Enum`），表示翻译任务在数据库中的生命周期状态。

引擎处理结果
------------

.. rubric:: EngineBatchItemResult

一个类型联合（`Union`），代表翻译引擎对单个文本的处理结果。它只能是 :class:`EngineSuccess` 或 :class:`EngineError` 之一。

.. autoclass:: EngineSuccess
   :members:
   :undoc-members: false
   :show-inheritance:

   表示单个文本翻译成功。`from_cache` 标志指示结果是否来自**翻译引擎自身**的内部缓存（而非 `Coordinator` 的缓存）。

.. autoclass:: EngineError
   :members: error_message is_retryable
   :undoc-members: false
   :show-inheritance:

   表示单个文本翻译失败。`is_retryable` 是一个关键标志，`Coordinator` 将根据此标志决定是否对临时性错误进行重试。

.. _types-translation-request:

内部翻译请求
------------

.. autoclass:: TranslationRequest
   :members:
   :undoc-members: false
   :show-inheritance:

   表示一个内部传递或用于缓存查找的翻译请求单元。

最终翻译结果
------------

.. autoclass:: TranslationResult
   :members:
   :undoc-members: false
   :show-inheritance:
   
   这是 `Coordinator` 返回给用户的最终结果对象。它聚合了来自数据库和翻译引擎的所有相关信息。
   `from_cache` 标志指示此结果是否来自 `Trans-Hub` 的缓存（内存缓存或数据库），从而表示并未发生实时的 API 调用。

内部待办任务项
--------------

.. autoclass:: ContentItem
   :members:
   :undoc-members: false
   :show-inheritance:

   一个内部 DTO，代表 `Coordinator` 从 `PersistenceHandler` 获取的、待翻译的单个任务单元。

全局上下文哨兵
----------------

.. autoattribute:: trans_hub.types.GLOBAL_CONTEXT_SENTINEL

   一个特殊的字符串常量，当翻译请求没有提供上下文时，用作 `context_hash` 的值。这确保了 `context_hash` 字段在数据库中始终为非空，从而使 `UNIQUE` 约束能够正确工作。