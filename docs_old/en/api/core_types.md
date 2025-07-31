# **API Reference: Core Types**

**Module**: `trans_hub.types`

This document is the authoritative reference for all core Data Transfer Objects (DTOs) defined in the `trans_hub.types` module. These Pydantic models form the foundation of the internal data flow in `Trans-Hub`.

[Return to Document Index](../INDEX.md)

## **`TranslationStatus`**

A string enumeration (`Enum`) that represents the lifecycle status of a translation task in the database.

- **`PENDING`**: The task has been registered and is waiting to be processed.
- **`TRANSLATING`**: The task is being processed by the `Coordinator` and has been locked.
- **`TRANSLATED`**: The task has been successfully translated.
- **`FAILED`**: The task failed during the translation process (possibly after multiple retries).
- **`APPROVED`**: (Reserved status) The translation result has been manually reviewed or approved.

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

## **`TranslationResult`**

This is the final result object returned to the user by the `Coordinator`. It aggregates all relevant information from the database and the translation engine.

- **`original_content`** (`str`): The original text to be translated.
- **`translated_content`** (`Optional[str]`): The translated text. If the translation fails, this field is `None`.
- **`target_lang`** (`str`): The target language code (e.g., 'zh-CN').
- **`status`** (`TranslationStatus`): The status of the translation task. When returned by the `Coordinator`, it is usually `TRANSLATED` or `FAILED`.
- **`engine`** (`Optional[str]`): The name of the engine that performed this translation.
- **`from_cache`** (`bool`): A key flag. If `True`, it indicates that this result comes from the cache of `Trans-Hub` (memory cache or database) and was not translated through a real-time API call to the translation engine. If `False`, it indicates that this is a newly generated translation in this workflow.
- **`error`** (`Optional[str]`): If the translation fails, this field contains the error message.
- **`context_hash`** (`str`): The hash value of the context associated with this translation. For translations without context, its value is `GLOBAL_CONTEXT_SENTINEL`.
- **`business_id`** (`Optional[str]`): The business ID associated with this translation. If the task is ad-hoc translation or the association has been garbage collected, it is `None`.

## **`ContentItem`**

An internal DTO that represents a single task unit to be translated, obtained by the `Coordinator` from the `PersistenceHandler`.

- **`content_id`** (`int`): The unique ID of the text in the `th_content` table.
- **`value`** (`str`): The original text content.
- **`context_hash`** (`str`): The hash value of the context.
- **`context`** (`Optional[dict]`): The original context dictionary associated with this task, which the `Coordinator` passes to the engine.

## **Constant**

### **`GLOBAL_CONTEXT_SENTINEL`**

- **Type**: `str`
- **Value**: `__GLOBAL__`
- **Usage**: A special string constant used as the value of `context_hash` when no context is provided for the translation request. This ensures that the `context_hash` field is always non-empty in the database, allowing the `UNIQUE` constraint to function correctly.
