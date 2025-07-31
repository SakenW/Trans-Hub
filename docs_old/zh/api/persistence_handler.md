# **API 参考：PersistenceHandler**

**模块**: `trans_hub.interfaces`  
**协议**: `PersistenceHandler`

本文档是 `PersistenceHandler` 协议的权威 API 参考。`PersistenceHandler` 是 `Trans-Hub` 中所有数据持久化操作的**抽象接口**。

任何希望为 `Trans-Hub` 提供自定义存储后端（例如 PostgreSQL, MySQL）的开发者，都必须实现这个协议中定义的所有异步方法。

[返回文档索引](../INDEX.md)

---

## **设计哲学**

- **纯异步**: `PersistenceHandler` 是一个**纯异步**的接口。所有的方法都必须是 `async def`，并且不能执行任何阻塞 I/O 操作。
- **事务性**: 所有改变数据库状态的写操作（如创建任务、保存结果）都应该是**原子性**的，以保证数据的一致性。
- **并发安全 (Concurrency-Safe)**: `PersistenceHandler` 的实现**必须**保证其所有公共方法都是并发安全的。对于像 SQLite 这样不支持并发写事务的后端，实现者**必须**在内部使用锁或其他机制来串行化写操作。
- **职责单一**: `PersistenceHandler` 的实现只负责与数据库的直接交互。它不应该包含任何业务逻辑（如重试、缓存查找），这些都由 `Coordinator` 负责。

## **生命周期方法**

### `connect()`

```python
async def connect(self) -> None:
```

**描述**:
建立并配置到底层数据库的连接。这是在 `Coordinator.initialize()` 期间被调用的第一个方法。一个健壮的实现应该在这里设置好连接池、PRAGMA 指令等。

**返回**:
`None`

### `close()`

```python
async def close(self) -> None:
```

**描述**:
优雅地关闭所有数据库连接并释放相关资源。这是在 `Coordinator.close()` 期间被调用的方法。

**返回**:
`None`

## **核心数据流方法**

### `ensure_pending_translations()`

```python
async def ensure_pending_translations(
    self,
    text_content: str,
    target_langs: list[str],
    source_lang: Optional[str],
    engine_version: str,
    business_id: Optional[str] = None,
    context_hash: Optional[str] = None,
    context_json: Optional[str] = None,
) -> None:
```

**描述**:
这是 `Coordinator.request()` 调用的核心方法。它负责在一个**单一的原子事务**中完成以下所有操作：

1.  确保 `text_content` 在 `th_content` 表中存在，如果不存在则创建，并获取其 `content_id`。
2.  如果提供了 `business_id`，则在 `th_sources` 表中创建或更新其与 `content_id` 和 `context_hash` 的关联，并更新 `last_seen_at` 时间戳。
3.  对于 `target_langs` 中的每一种语言，如果 `th_translations` 表中尚不存在一个**已完成**的翻译记录（状态为 `TRANSLATED`），则创建一条新的 `PENDING` 记录。

**参数**:

- `text_content` (`str`): 原始文本。
- `target_langs` (`list[str]`): 目标语言列表。
- `source_lang` (`Optional[str]`): 源语言代码。
- `engine_version` (`str`): 当前活动引擎的版本号。
- `business_id` (`Optional[str]`): 业务 ID。
- `context_hash` (`Optional[str]`): 上下文哈希。
- `context_json` (`Optional[str]`): 原始上下文的 JSON 字符串表示。

**返回**:
`None`

### `stream_translatable_items()`

```python
async def stream_translatable_items(
    self,
    lang_code: str,
    statuses: list[TranslationStatus],
    batch_size: int,
    limit: Optional[int] = None,
) -> AsyncGenerator[list[ContentItem], None]:
```

**描述**:
一个异步生成器，用于从数据库中流式地获取待翻译的任务批次。

对于每个批次，实现**必须**在一个**原子事务**中完成以下两步：

1.  查找一批符合 `lang_code` 和 `statuses` 条件的翻译任务。
2.  **立即**将这些被选中的任务的状态更新为 `TRANSLATING`，以防止其他并行的 `Coordinator` 实例重复获取相同的任务。

在事务**成功提交后**，再 `yield` 出 `ContentItem` 的列表。

**参数**:

- `lang_code` (`str`): 目标语言。
- `statuses` (`list[TranslationStatus]`): 要查询的任务状态列表 (通常是 `[PENDING, FAILED]`)。
- `batch_size` (`int`): 每个批次的最大数量。
- `limit` (`Optional[int]`): 本次调用最多获取的任务总数。

**Yields**:

- `list[ContentItem]`: 一批待翻译的任务。生成器每次 `yield` 的是一个列表，其长度不超过 `batch_size`。

### `save_translations()`

```python
async def save_translations(self, results: list[TranslationResult]) -> None:
```

**描述**:
将一批已完成的 `TranslationResult` 对象原子性地保存回数据库。实现应该在一个**单一的事务**中，根据 `content_id`, `lang_code`, 和 `context_hash` 找到对应的记录，并更新其 `status`, `translation_content`, `engine` 等字段。

**参数**:

- `results` (`list[TranslationResult]`): 从 `Coordinator` 传来的、已完成的翻译结果列表。

**返回**:
`None`

## **辅助查询方法**

### `get_translation()`

```python
async def get_translation(
    self, text_content: str, target_lang: str, context: Optional[dict[str, Any]] = None,
) -> Optional[TranslationResult]:
```

**描述**:
一个只读方法，用于直接从持久化层查询一个**已完成**的翻译结果。这通常用于快速响应用户请求，绕过 `request` -> `process` 的完整流程。

实现应该根据 `text_content`, `target_lang`, 和 `context`（需要先计算其哈希）来查找唯一匹配的、状态为 `TRANSLATED` 的记录。

**返回**:

- `Optional[TranslationResult]`: 如果找到，则返回一个 `TranslationResult` 对象；否则返回 `None`。

### `get_business_id_for_content()`

```python
async def get_business_id_for_content(
    self, content_id: int, context_hash: str
) -> Optional[str]:
```

**描述**:
一个只读方法，根据 `content_id` 和 `context_hash` 的**唯一组合**从 `th_sources` 表中查找对应的 `business_id`。这是 `Coordinator` 进行性能优化的关键辅助方法，用于在处理批次前预加载所有业务 ID。

**返回**:

- `Optional[str]`: 如果找到，则返回 `business_id` 字符串；否则返回 `None`。

## **维护方法**

### `touch_source()`

```python
async def touch_source(self, business_id: str) -> None:
```

**描述**:
将 `th_sources` 表中指定 `business_id` 的 `last_seen_at` 时间戳更新为当前时间。

**返回**:
`None`

### `garbage_collect()`

```python
async def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict[str, int]:
```

**描述**:
执行数据清理。详见 [数据模型文档](../architecture/02_data_model.md#3-垃圾回收-gc)。

**返回**:

- `dict[str, int]`: 一个包含清理统计的字典，例如 `{'deleted_sources': 10, 'deleted_content': 5}`。
