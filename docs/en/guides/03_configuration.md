# Guide 3: Configure Deep Parsing

Welcome to the in-depth configuration guide for `Trans-Hub`. This document will provide a detailed introduction to the `TransHubConfig` object and all its sub-configuration models, and explain how to customize the behavior of `Trans-Hub` using Python code, environment variables, or a `.env` file.

[Return to Document Index](../INDEX.md)

---

## **1. 核心理念：`TransHubConfig`**

`Trans-Hub` 的所有配置都由一个核心的 Pydantic 模型 `TransHubConfig` 管理。这是所有配置的“单一事实来源”。你应该在你的应用初始化时创建一个 `TransHubConfig` 实例，并将其传递给 `Coordinator`。

**基本用法**:

```python
from trans_hub.config import TransHubConfig

# 创建一个使用所有默认设置的配置对象
default_config = TransHubConfig()

# 创建一个自定义配置的对象
custom_config = TransHubConfig(
    active_engine="openai",
    source_lang="en",
    batch_size=100
)
```

---

## **2. Top-level Configuration Parameters**

These parameters can be set directly when initializing `TransHubConfig`.

- **`database_url`** (`str`)

  - **Description**: Specifies the connection string for the database used by `Trans-Hub`.
  - **Default value**: `"sqlite:///transhub.db"`
  - **Example**:

    ```python
    # 使用一个位于 /var/data/ 的持久化数据库文件
    config = TransHubConfig(database_url="sqlite:////var/data/my_app_translations.db")

    # Use in-memory database (for testing only, data will not be persisted)
    config = TransHubConfig(database_url="sqlite:///:memory:")

- **`active_engine`** (`str`)

  - **Description**: Specifies the translation engine that the `Coordinator` activates by default at startup. This value must match the registered name of an engine in the `trans_hub/engines` directory (usually the filename).
  - **Default value**: `"translators"`
  - **Example**: `TransHubConfig(active_engine="openai")`

- **`batch_size`** (`int`)

  - **Description**: In the `process_pending_translations` workflow, the size of the batch of pending tasks retrieved from the database each time.
  - **Default value**: `50`
  - **Note**: The final batch size will also be limited by the engine's own `max_batch_size`.

- **`source_lang`** (`Optional[str]`)

  - **Description**: The global default source language code (e.g., `"en"`, `"zh"`). This configuration is very important for engines that require an explicit source language (such as `OpenAIEngine`).
  - **Default value**: `None`

- **`gc_retention_days`** (`int`)
  - **Description**: The default data retention period for garbage collection (GC) in days. `run_garbage_collection` will use this value when the `expiration_days` parameter is not specified.
  - **Default value**: `90`

---

## **3. 子配置模型**

`TransHubConfig` 通过组合多个子配置模型来管理不同模块的行为。你可以通过创建子模型的实例并将其传递给 `TransHubConfig` 来进行深度定制。

### **3.1 `cache_config: CacheConfig`**

控制 `Coordinator` 内部的内存缓存（L1 缓存）行为。

- **`maxsize`** (`int`): 缓存中可以存储的最大项目数。
  - **默认值**: `1000`
- **`ttl`** (`int`): 缓存项目的生命周期（秒）。只在 `cache_type="ttl"` 时有效。
  - **默认值**: `3600` (1 小时)
- **`cache_type`** (`str`): 缓存策略。可以是 `"ttl"` (基于时间过期) 或 `"lru"` (最近最少使用淘汰)。
  - **默认值**: `"ttl"`

**示例**:

```python
from trans_hub.cache import CacheConfig

# 创建一个能容纳 10000 个项目、有效期为 24 小时的 LRU 缓存配置
custom_cache = CacheConfig(maxsize=10000, ttl=86400, cache_type="lru")

config = TransHubConfig(cache_config=custom_cache)
```

### **3.2 `retry_policy: RetryPolicyConfig`**

定义 `Coordinator` 在遇到可重试错误时的重试策略。

- **`max_attempts`** (`int`): 最大尝试次数（不包括第一次调用）。`2` 表示总共会尝试 3 次。
  - **默认值**: `2`
- **`initial_backoff`** (`float`): 首次重试前的初始等待时间（秒）。
  - **默认值**: `1.0`
- **`max_backoff`** (`float`): 指数退避策略下的最大等待时间上限（秒）。
  - **默认值**: `60.0`

### **3.3 `logging: LoggingConfig`**

配置 `structlog` 日志系统的行为。

- **`level`** (`str`): 日志级别，如 `"DEBUG"`, `"INFO"`, `"WARNING"`。
  - **默认值**: `"INFO"`
- **`format`** (`str`): 日志输出格式。`"console"` 适用于开发环境（带颜色），`"json"` 适用于生产环境。
  - **默认值**: `"console"`

### **3.4 `engine_configs: EngineConfigs`**

这是一个特殊的子模型，用于聚合所有特定引擎的配置。

**通常，你不需要手动创建 `EngineConfigs` 实例。** `TransHubConfig` 的智能验证器会自动为你创建和填充它。

但是，如果你需要为一个**非激活**的引擎提供特定的启动配置（例如，为了之后通过 `switch_engine` 切换到它），你可以这样做：

```python
from trans_hub.config import EngineConfigs
from trans_hub.engines.openai import OpenAIEngineConfig

# 手动为 OpenAI 引擎提供一个自定义模型
openai_config = OpenAIEngineConfig(
    openai_model="gpt-4-turbo",
    # openai_api_key 会自动从 .env 加载
)

# 默认激活 translators，但同时为 openai 提供了预配置
config = TransHubConfig(
    active_engine="translators",
    engine_configs=EngineConfigs(
        openai=openai_config
    )
)
```

---

## **4. Configuration through environment variables and `.env` files**

Trans-Hub" extensively uses "pydantic-settings", which means that many configurations (especially those that inherit from "BaseSettings") can be set through environment variables or the ".env" file in the project root directory.

### **Naming Conventions**

The name of the environment variable is composed of **prefix** + **configuration path**.

- **Default Prefix**: `TH_` (used for `OpenAIEngineConfig` etc.)
- **Configuration Path**: Field names are connected by underscores `_`.

### **Example**

Assuming you want to override the `openai_model` and `temperature` of `OpenAIEngine`.

**In the `.env` file:**

```dotenv
# .env
TH_OPENAI_API_KEY="sk-..."
TH_OPENAI_MODEL="gpt-4-turbo"
TH_OPENAI_TEMPERATURE="0.5"
```

When your application creates `TransHubConfig(active_engine="openai")`, the `OpenAIEngineConfig` instance will automatically read these values.

### **Priority Order**

The configuration loading of Pydantic Settings follows the following priority order (from high to low):

1. **Parameters initialized directly in the code** (e.g., `OpenAIEngineConfig(openai_model="...")`)  
2. **Environment variables** (e.g., `export TH_OPENAI_MODEL="..."`)  
3. **Values in the `.env` file**  
4. **Default values defined in the configuration model**

This provides you with great flexibility to use different configurations in different environments (development, testing, production) without having to modify any code.
