# **API Reference: PersistenceHandler**

**Module**: `trans_hub.interfaces`  
**Protocol**: `PersistenceHandler`

This document is the authoritative API reference for the `PersistenceHandler` protocol. `PersistenceHandler` is the **abstract interface** for all data persistence operations in `Trans-Hub`.

Any developer who wishes to provide a custom storage backend for `Trans-Hub` (such as PostgreSQL, MySQL) must implement all the asynchronous methods defined in this protocol.

[Return to Document Index](../INDEX.md)

## **Design Philosophy**

- **Pure Asynchronous**: `PersistenceHandler` is a **pure asynchronous** interface. All methods must be `async def` and cannot perform any blocking I/O operations.
- **Transactional**: All write operations that change the database state (such as creating tasks, saving results) should be **atomic** to ensure data consistency.
- **Concurrency-Safe**: The implementation of `PersistenceHandler` **must** ensure that all its public methods are concurrency-safe. For backends like SQLite that do not support concurrent write transactions, implementers **must** use locks or other mechanisms internally to serialize write operations.
- **Single Responsibility**: The implementation of `PersistenceHandler` is only responsible for direct interaction with the database. It should not contain any business logic (such as retries, cache lookups), which are the responsibility of the `Coordinator`.

## **Lifecycle Methods**

### `connect()`

```python
async def connect(self) -> None:
```

**Description**: Establish and configure the connection to the underlying database. This is the first method called during `Coordinator.initialize()`. A robust implementation should set up the connection pool, PRAGMA directives, etc., here.

**Return**: `None`

### `close()`

```python
async def close(self) -> None:
```

**Description**: Elegantly close all database connections and release related resources. This is the method called during `Coordinator.close()`.

**Return**: `None`

## **Core Data Flow Method**

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

**Description**: This is the core method of the `Coordinator.request()` call. It is responsible for completing all the following operations in a **single atomic transaction**:

1. Ensure that `text_content` exists in the `th_content` table; if it does not exist, create it and obtain its `content_id`.  
2. If a `business_id` is provided, create or update its association with `content_id` and `context_hash` in the `th_sources` table, and update the `last_seen_at` timestamp.  
3. For each language in `target_langs`, if there is no **completed** translation record (status `TRANSLATED`) in the `th_translations` table, create a new `PENDING` record.

**Parameters:**

- `text_content` (`str`): Original text.
- `target_langs` (`list[str]`): List of target languages.
- `source_lang` (`Optional[str]`): Source language code.
- `engine_version` (`str`): Version number of the currently active engine.
- `business_id` (`Optional[str]`): Business ID.
- `context_hash` (`Optional[str]`): Context hash.
- `context_json` (`Optional[str]`): JSON string representation of the original context.

**Return**: `None`

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

**Description**: An asynchronous generator for streaming batches of translation tasks from the database.

For each batch, it is **necessary** to complete the following two steps in an **atomic transaction**:

1. Find a batch of translation tasks that meet the conditions of `lang_code` and `statuses`.  
2. **Immediately** update the status of these selected tasks to `TRANSLATING` to prevent other parallel `Coordinator` instances from retrieving the same tasks.

After the transaction **is successfully submitted**, yield the list of `ContentItem`.

**Parameters:**

- `lang_code` (`str`): Target language.
- `statuses` (`list[TranslationStatus]`): List of task statuses to query (usually `[PENDING, FAILED]`).
- `batch_size` (`int`): Maximum number per batch.
- `limit` (`Optional[int]`): Maximum total number of tasks to retrieve in this call.

**Yields**:

- `list[ContentItem]`: A batch of tasks to be translated. The generator yields a list each time, with a length not exceeding `batch_size`.

### `save_translations()`

```python
async def save_translations(self, results: list[TranslationResult]) -> None:
```

**Description**: Atomically save a batch of completed `TranslationResult` objects back to the database. The implementation should find the corresponding records based on `content_id`, `lang_code`, and `context_hash` in a **single transaction**, and update fields such as `status`, `translation_content`, and `engine`.

**Parameters:**

- `results` (`list[TranslationResult]`): A list of completed translation results received from the `Coordinator`.

**Return**: `None`

## **Auxiliary Query Methods**

### `get_translation()`

```python
async def get_translation(
    self, text_content: str, target_lang: str, context: Optional[dict[str, Any]] = None,
) -> Optional[TranslationResult]:
```

**Description**: A read-only method for directly querying a **completed** translation result from the persistence layer. This is typically used for quickly responding to user requests, bypassing the full `request` -> `process` flow.

The implementation should find a uniquely matched record with a status of `TRANSLATED` based on `text_content`, `target_lang`, and `context` (which needs to be hashed first).

**Return**:

- `Optional[TranslationResult]`: Returns a `TranslationResult` object if found; otherwise returns `None`.

### `get_business_id_for_content()`

```python
async def get_business_id_for_content(
    self, content_id: int, context_hash: str
) -> Optional[str]:
```

**Description**: A read-only method that looks up the corresponding `business_id` from the `th_sources` table based on the **unique combination** of `content_id` and `context_hash`. This is a key auxiliary method for the `Coordinator` to optimize performance, used to preload all business IDs before processing batches.

**Return**:

- `Optional[str]`: Returns the `business_id` string if found; otherwise returns `None`.

## **Maintenance Methods**

### `touch_source()`

```python
async def touch_source(self, business_id: str) -> None:
```

**Description**: Update the `last_seen_at` timestamp for the specified `business_id` in the `th_sources` table to the current time.

**Return**: `None`

### `garbage_collect()`

```python
async def garbage_collect(self, retention_days: int, dry_run: bool = False) -> dict[str, int]:
```

**Description**: Execute data cleaning. See [Data Model Documentation](../architecture/02_data_model.md#3-garbage-collection-gc) for details.

**Return**:

- `dict[str, int]`: A dictionary containing cleanup statistics, for example `{'deleted_sources': 10, 'deleted_content': 5}`.
