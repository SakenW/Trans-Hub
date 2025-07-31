# **API Reference: Coordinator**

**Module**: `trans_hub.coordinator`  
**Class**: `Coordinator`

This document is the authoritative API reference for the `Coordinator` class. The `Coordinator` is the core orchestrator of `Trans-Hub` and is the main entry point for interacting with the system.

[Return to Document Index](../INDEX.md)

## **Overview**

Coordinator" is a **purely asynchronous** class responsible for managing the entire translation lifecycle. Its core responsibilities include:

- Receive translation requests.
- Pull pending tasks from the persistence layer.
- Invoke the currently active translation engine.
- Apply retry, caching, and rate limiting strategies.
- Write the final results back to the persistence layer.

## **Initialization**

### `__init__(...)`

```python
def __init__(
    self,
    config: TransHubConfig,
    persistence_handler: PersistenceHandler,
    rate_limiter: Optional[RateLimiter] = None,
) -> None:
```

**Description**: The constructor of `Coordinator`. This is a synchronous method responsible for receiving all dependencies and performing internal setup. **This method does not perform any I/O operations.** The created `Coordinator` instance is **state-independent** (except for the held configuration and dependencies), so it can be safely reused in your application.

**Parameters:**

- **`config`** (`TransHubConfig`): A complete `TransHubConfig` object. The `Coordinator` will read all behavior configurations from this object.
- **`persistence_handler`** (`PersistenceHandler`): An instance of a pure asynchronous persistence handler that implements the `PersistenceHandler` protocol.
- **`rate_limiter`** (`Optional[RateLimiter]`): (optional) An instance of `RateLimiter`. If provided, the `Coordinator` will adhere to its rate limits before calling the engine.

## **Public Methods**

### `initialize()`

```python
async def initialize(self) -> None:
```

**Description**: Asynchronous initialization of `Coordinator`. **This method must be `await`ed before performing any other operations.** Its main responsibility is to establish and configure the connection to the underlying persistent storage (e.g., database).

**Return**: `None`

**Usage example**:

```python
from trans_hub.config import TransHubConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.coordinator import Coordinator

config = TransHubConfig()
handler = DefaultPersistenceHandler(db_path=config.db_path)
coordinator = Coordinator(config, handler)

# 在使用前必须异步初始化
await coordinator.initialize()
```

### `switch_engine()`

```python
def switch_engine(self, engine_name: str) -> None:
```

**Description**: Dynamically switch the currently active translation engine at runtime. This is a synchronous method.

**Important**: Due to the intelligent configuration loading mechanism of `TransHubConfig`, as long as the target engine's configuration can be automatically loaded from environment variables (e.g., `OpenAI`), or it does not require any special configuration (e.g., `translators`), this switching operation is usually successful.

**Parameters:**

- **`engine_name`** (`str`): The name of the engine to switch to (e.g., `"openai"`, `"translators"`).

**Return**: `None`

**Usage example**:

```python
# 假设 coordinator 最初使用 'translators' 引擎
coordinator.switch_engine("openai")
# 现在 coordinator 的所有后续翻译都将使用 OpenAI 引擎
```

### `request()`

```python
async def request(
    self,
    target_langs: list[str],
    text_content: str,
    business_id: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    source_lang: Optional[str] = None,
) -> None:
```

**Description**: A lightweight asynchronous method for **registering** one or more translation tasks. It ensures that the corresponding pending (`PENDING`) tasks exist in the database.

This method **does not perform** actual translation, so the response speed is very fast, making it very suitable for use in high-concurrency scenarios such as web request handling.

**Parameters:**

- **`target_langs`** (`list[str]`): A list of one or more target language codes (e.g. `['zh-CN', 'ja']`).
- **`text_content`** (`str`): The original text that needs to be translated.
- **`business_id`** (`Optional[str]`): (Optional) A unique ID associated with this text in your business.
- **`context`** (`Optional[dict]`): (Optional) A dictionary providing additional translation context.
- **`source_lang`** (`Optional[str]`): (Optional) Explicitly specify the source language. If provided, it will override the `source_lang` in the global configuration.

**Return**: `None`

### `process_pending_translations()`

```python
async def process_pending_translations(
    self,
    target_lang: str,
    batch_size: Optional[int] = None,
    limit: Optional[int] = None,
    max_retries: Optional[int] = None,
    initial_backoff: Optional[float] = None,
) -> AsyncGenerator[TranslationResult, None]:
```

**Description**: An **asynchronous generator** is the core "working engine" of `Trans-Hub`. It streams pending (`PENDING`) or failed (`FAILED`) tasks in the specified language from the database, processes them in batches, and yields a `TranslationResult` object after each task is completed.

This is a method that may run for a long time, and it is strongly recommended to run it in a **background task**.

**Parameters:**

- **`target_lang`** (`str`): The target language code you wish to process.
- **`batch_size`** (`Optional[int]`): (Optional) The number of tasks to pull from the database at a time. Defaults to `config.batch_size`.
- **`limit`** (`Optional[int]`): (Optional) The maximum total number of tasks to process in this call.
- `max_retries`, `initial_backoff`: (Optional) Override the retry strategy in the global configuration.

**Yields**:

- `TranslationResult`: A `TranslationResult` object is created whenever a translation task (successful or failed) is completed. The generator will terminate normally after all eligible tasks have been processed.

**Usage example**:

```python
async def process_all_chinese_tasks(coordinator: Coordinator):
    print("开始处理所有中文翻译...")
    processed_count = 0
    async for result in coordinator.process_pending_translations(target_lang="zh-CN"):
        if result.status == TranslationStatus.TRANSLATED:
            print(f"成功: '{result.original_content}' -> '{result.translated_content}'")
        else:
            print(f"失败: '{result.original_content}', 错误: {result.error}")
        processed_count += 1
    print(f"处理完成，共处理了 {processed_count} 个任务。")
```

### `get_translation()`

```python
async def get_translation(
    self,
    text_content: str,
    target_lang: str,
    context: Optional[dict[str, Any]] = None,
) -> Optional[TranslationResult]:
```

**Description**: An efficient read-only method for directly obtaining a **completed** translation result.

This method is the best way to obtain translated content, as it implements a **two-level caching query strategy**:

1. First, check the high-speed **memory cache (L1 Cache)**.  
2. If the memory cache is not hit, query the **persistent storage (L2 Cache / database)**.  
3. If a result is found in the database, it will automatically **fill back** into the memory cache to speed up subsequent queries.

This is very useful for scenarios that require frequent queries for the same translation (such as in web requests).

**Parameters:**

- **`text_content`** (`str`): The original text to be queried.
- **`target_lang`** (`str`): Target language code.
- **`context`** (`Optional[dict[str, Any]]`): (Optional) Translation context used to distinguish translations in different situations.

**Return**:

- `Optional[TranslationResult]`: If a completed translation is found in any layer of the cache, return a `TranslationResult` object; otherwise, return `None`.

### `run_garbage_collection()`

```python
async def run_garbage_collection(
    self,
    expiration_days: Optional[int] = None,
    dry_run: bool = False,
) -> dict[str, int]:
```

**Description**: Asynchronous execution of the garbage collection (GC) process to clean up outdated and inactive business association records in the database. It is recommended to run this regularly in a separate maintenance script or scheduled task.

**Parameters:**

- **`expiration_days`** (`Optional[int]`): (Optional) Retention period (days). Business associations with a `last_seen_at` timestamp older than this number of days will be cleaned up. Defaults to `config.gc_retention_days`.
- **`dry_run`** (`bool`): If set to `True`, it will only report the number of records that will be deleted, without actually performing the deletion. Defaults to `False`.

**Return**:

- `dict[str, int]`: A dictionary containing cleanup statistics, for example `{'deleted_sources': 10, 'deleted_content': 5}`.

### `close()`

```python
async def close(self) -> None:
```

**Description**: Asynchronously and gracefully shut down the `Coordinator` and all resources it holds, primarily the underlying database connections. **This method must be called before your application closes** to ensure that all resources are properly released.

**Return**: `None`

**Usage Example (Best Practices):**

```python
async def main():
    coordinator = None
    try:
        coordinator = await initialize_trans_hub()
        # ... 在这里执行您的应用逻辑 ...
        await coordinator.request(...)
        # ...
    finally:
        # 确保无论发生什么，资源都会被关闭
        if coordinator:
            await coordinator.close()

if __name__ == "__main__":
    asyncio.run(main())
```
