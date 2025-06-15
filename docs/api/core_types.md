# **API 参考：核心类型**

本文档是 `trans_hub.types` 模块中定义的所有核心数据传输对象（DTOs）的权威参考。这些 Pydantic 模型构成了 `Trans-Hub` 内部数据流的基础。

---

## **`TranslationStatus`**

一个字符串枚举（`StrEnum`），表示翻译任务的当前状态。

- **`PENDING`**: 任务已登记，等待被处理。
- **`TRANSLATING`**: 任务正在被 `Coordinator` 处理中。
- **`TRANSLATED`**: 任务已成功翻译并缓存。
- **`FAILED`**: 任务在翻译过程中失败（可能在多次重试后）。
- **`APPROVED`**: (预留状态) 翻译结果已经过人工审核或批准。

---

## **`EngineBatchItemResult`**

一个类型联合（`Union`），代表翻译引擎对单个文本的处理结果。它只能是 `EngineSuccess` 或 `EngineError` 之一。

### **`EngineSuccess`**

表示单个文本翻译成功。

- **`translated_text`** (`str`): 翻译后的文本。

### **`EngineError`**

表示单个文本翻译失败。

- **`error_message`** (`str`): 描述错误的文本信息。
- **`is_retryable`** (`bool`): 一个关键标志，指示此错误是否是临时性的（如网络问题、服务器 5xx 错误），`Coordinator` 将根据此标志决定是否重试整个批次。

---

## **`TranslationResult`**

这是 `Coordinator.process_pending_translations()` 返回给用户的最终结果对象。它聚合了来自数据库和翻译引擎的所有相关信息。

- **`original_content`** (`str`): 被翻译的原始文本。
- **`translated_content`** (`Optional[str]`): 翻译后的文本。如果翻译失败，此字段为 `None`。
- **`target_lang`** (`str`): 目标语言代码 (例如, 'zh-CN')。
- **`status`** (`TranslationStatus`): 翻译任务的最终状态 (`TRANSLATED` 或 `FAILED`)。
- **`engine`** (`str`): 执行此次翻译的引擎名称。
- **`from_cache`** (`bool`): 指示此结果是否直接从缓存中获取。通过 `process_pending_translations` 返回的结果此字段始终为 `False`。
- **`error`** (`Optional[str]`): 如果翻译失败，此字段包含错误信息。
- **`context_hash`** (`str`): 与此翻译关联的上下文的哈希值。对于无上下文的翻译，其值为 `__GLOBAL__`。
- **`business_id`** (`Optional[str]`): 与此翻译关联的业务 ID。如果没有找到关联，或任务是即席翻译，则为 `None`。

---

## **`ContentItem`**

一个内部 DTO，代表 `Coordinator` 从 `PersistenceHandler` 获取的、待翻译的单个任务单元。

- **`content_id`** (`int`): 文本在 `th_content` 表中的唯一 ID。
- **`value`** (`str`): 原始文本内容。
- **`context_hash`** (`str`): 上下文的哈希值。
- **`context`** (`Optional[dict]`): 与此任务关联的原始上下文字典。这是 `Coordinator` 能够将上下文传递给引擎的关键。

---

## **常量**

### **`GLOBAL_CONTEXT_SENTINEL`**

- **类型**: `str`
- **值**: `__GLOBAL__`
- **用途**: 一个特殊的字符串常量，当翻译请求没有提供上下文时，用作 `context_hash` 的值。这确保了 `context_hash` 字段在数据库中始终为非空，从而使 `UNIQUE` 约束能够正确工作。
