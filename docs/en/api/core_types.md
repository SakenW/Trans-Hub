# **API Reference: Core Types**

**Module**: `trans_hub.types`

This document is the authoritative reference for all core Data Transfer Objects (DTOs) defined in the `trans_hub.types` module. These Pydantic models form the foundation of the internal data flow in `Trans-Hub`.

[Return to Document Index](../INDEX.md)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **`TranslationStatus`**

一个字符串枚举（`Enum`），表示翻译任务在数据库中的生命周期状态。

- **`PENDING`**: 任务已登记，等待被处理。
- **`TRANSLATING`**: 任务正在被 `Coordinator` 处理中，已被锁定。
- **`TRANSLATED`**: 任务已成功翻译。
- **`FAILED`**: 任务在翻译过程中失败（可能在多次重试后）。
- **`APPROVED`**: (预留状态) 翻译结果已经过人工审核或批准。

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **`EngineBatchItemResult`**

A type union (`Union`) that represents the processing result of a translation engine for a single text. It can only be either `EngineSuccess` or `EngineError`.

### **`EngineSuccess`**

Indicates that the translation of a single text was successful.

- **`translated_text`** (`str`): The translated text.
- **`from_cache`** (`bool`): A flag indicating whether the result comes from the **translation engine's own** internal cache (as opposed to the `Coordinator`'s cache). Defaults to `False`.

### **`EngineError`**

Indicates that the translation of a single text has failed.

- **`error_message`** (`str`): A text message describing the error.
- **`is_retryable`** (`bool`): A key flag indicating whether this error is temporary (e.g., network issues, server `5xx` errors). The `Coordinator` will decide whether to retry based on this flag.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **`TranslationResult`**

这是 `Coordinator` 返回给用户的最终结果对象。它聚合了来自数据库和翻译引擎的所有相关信息。

- **`original_content`** (`str`): 被翻译的原始文本。
- **`translated_content`** (`Optional[str]`): 翻译后的文本。如果翻译失败，此字段为 `None`。
- **`target_lang`** (`str`): 目标语言代码 (例如, 'zh-CN')。
- **`status`** (`TranslationStatus`): 翻译任务的状态。由 `Coordinator` 返回时，通常是 `TRANSLATED` 或 `FAILED`。
- **`engine`** (`Optional[str]`): 执行此次翻译的引擎名称。
- **`from_cache`** (`bool`): 一个关键标志。如果为 `True`，表示此结果来自 `Trans-Hub` 的缓存（内存缓存或数据库），并未通过实时 API 调用翻译引擎。如果为 `False`，表示这是本次工作流中新产生的翻译。
- **`error`** (`Optional[str]`): 如果翻译失败，此字段包含错误信息。
- **`context_hash`** (`str`): 与此翻译关联的上下文的哈希值。对于无上下文的翻译，其值为 `GLOBAL_CONTEXT_SENTINEL`。
- **`business_id`** (`Optional[str]`): 与此翻译关联的业务 ID。如果任务是即席翻译或关联已被 GC，则为 `None`。

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **`ContentItem`**

An internal DTO that represents a single task unit to be translated, obtained by the `Coordinator` from the `PersistenceHandler`.

- **`content_id`** (`int`): The unique ID of the text in the `th_content` table.
- **`value`** (`str`): The original text content.
- **`context_hash`** (`str`): The hash value of the context.
- **`context`** (`Optional[dict]`): The original context dictionary associated with this task, which the `Coordinator` will pass to the engine.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **Constant**

### **`GLOBAL_CONTEXT_SENTINEL`**

- **Type**: `str`
- **Value**: `__GLOBAL__`
- **Usage**: A special string constant used as the value of `context_hash` when no context is provided for the translation request. This ensures that the `context_hash` field is always non-empty in the database, allowing the `UNIQUE` constraint to function correctly.
