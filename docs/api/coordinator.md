# **API 参考：Coordinator**

**模块**: `trans_hub.coordinator`  
**类**: `Coordinator`

本文档是 `Coordinator` 类的权威 API 参考。`Coordinator` 是 `Trans-Hub` 的核心编排器，是您与系统交互的主要入口点。

[返回文档索引](../INDEX.md)

---

## **概述**

`Coordinator` 是一个**纯异步**的类，负责管理整个翻译生命周期。它的核心职责包括：

- 接收翻译请求。
- 从持久化层拉取待办任务。
- 调用当前活动的翻译引擎。
- 应用重试、缓存和速率限制策略。
- 将最终结果写回持久化层。

## **初始化**

### `__init__(...)`

```python
def __init__(
    self,
    config: TransHubConfig,
    persistence_handler: PersistenceHandler,
    rate_limiter: Optional[RateLimiter] = None,
) -> None:
```

**描述**:
`Coordinator` 的构造函数。这是一个同步方法，负责接收所有依赖项并进行内部设置。**此方法不执行任何 I/O 操作。** 创建的 `Coordinator` 实例是**状态无关**的（除了持有的配置和依赖），因此可以在您的应用中安全地复用。

**参数**:

- **`config`** (`TransHubConfig`): 一个完整的 `TransHubConfig` 对象。`Coordinator` 将从此对象中读取所有行为配置。
- **`persistence_handler`** (`PersistenceHandler`): 一个实现了 `PersistenceHandler` 协议的、纯异步的持久化处理器实例。
- **`rate_limiter`** (`Optional[RateLimiter]`): (可选) 一个 `RateLimiter` 实例。如果提供，`Coordinator` 将在调用引擎前遵守其速率限制。

---

## **公共方法**

### `initialize()`

```python
async def initialize(self) -> None:
```

**描述**:
异步初始化 `Coordinator`。**在执行任何其他操作之前，必须 `await` 此方法。** 它的主要职责是建立并配置到底层持久化存储（例如数据库）的连接。

**返回**:
`None`

**使用示例**:

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

**描述**:
在运行时动态地切换当前活动的翻译引擎。这是一个同步方法。

**重要**: 由于 `TransHubConfig` 的智能配置加载机制，只要目标引擎的配置可以从环境变量中自动加载（例如 `OpenAI`），或者它不需要任何特殊配置（例如 `translators`），此切换操作通常都能成功。

**参数**:

- **`engine_name`** (`str`): 要切换到的引擎的名称（例如 `"openai"`, `"translators"`）。

**返回**:
`None`

**使用示例**:

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

**描述**:
一个轻量级的异步方法，用于**登记**一个或多个翻译任务。它会确保相应的待处理（`PENDING`）任务存在于数据库中。

此方法**不执行**实际的翻译，因此响应速度非常快，非常适合在 Web 请求处理等高并发场景中使用。

**参数**:

- **`target_langs`** (`list[str]`): 一个或多个目标语言代码的列表 (例如 `['zh-CN', 'ja']`)。
- **`text_content`** (`str`): 需要翻译的原始文本。
- **`business_id`** (`Optional[str]`): (可选) 与此文本关联的、在您的业务中唯一的 ID。
- **`context`** (`Optional[dict]`): (可选) 一个提供额外翻译上下文的字典。
- **`source_lang`** (`Optional[str]`): (可选) 显式指定源语言。如果提供，它将覆盖全局配置中的 `source_lang`。

**返回**:
`None`

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

**描述**:
一个**异步生成器**，是 `Trans-Hub` 的核心“工作引擎”。它会从数据库中流式地拉取指定语言的待办（`PENDING`）或失败（`FAILED`）任务，分批处理它们，并在每个任务完成后 `yield` 一个 `TranslationResult` 对象。

这是一个可能长时间运行的方法，强烈建议在一个**后台任务**中运行它。

**参数**:

- **`target_lang`** (`str`): 您希望处理的目标语言代码。
- **`batch_size`** (`Optional[int]`): (可选) 每次从数据库中拉取的任务数量。默认为 `config.batch_size`。
- **`limit`** (`Optional[int]`): (可选) 本次调用最多处理的任务总数。
- `max_retries`, `initial_backoff`: (可选) 覆盖全局配置中的重试策略。

**Yields**:

- `TranslationResult`: 每当一个翻译任务（成功或失败）完成后，就会产生一个 `TranslationResult` 对象。当所有符合条件的任务都处理完毕后，生成器将正常结束。

**使用示例**:

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

### `run_garbage_collection()`

```python
async def run_garbage_collection(
    self,
    expiration_days: Optional[int] = None,
    dry_run: bool = False,
) -> dict[str, int]:
```

**描述**:
异步执行垃圾回收（GC）进程，清理数据库中过时和不再活跃的业务关联记录。建议在一个独立的维护脚本或定时任务中定期运行。

**参数**:

- **`expiration_days`** (`Optional[int]`): (可选) 保留期限（天）。`last_seen_at` 时间戳早于这个天数的业务关联将被清理。默认为 `config.gc_retention_days`。
- **`dry_run`** (`bool`): 如果为 `True`，将只报告将要删除的记录数量，而不会实际执行删除操作。默认为 `False`。

**返回**:

- `dict[str, int]`: 一个包含清理统计的字典，例如 `{'deleted_sources': 10, 'deleted_content': 5}`。

### `close()`

```python
async def close(self) -> None:
```

**描述**:
异步地、优雅地关闭 `Coordinator` 及其持有的所有资源，主要是底层的数据库连接。**在您的应用程序关闭前，必须调用此方法**，以确保所有资源都被正确释放。

**返回**:
`None`

**使用示例 (最佳实践)**:

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