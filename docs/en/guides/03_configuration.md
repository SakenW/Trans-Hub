# Guide 3: Configure Deep Parsing

Welcome to the in-depth configuration guide for `Trans-Hub`. This document will provide a detailed introduction to the `TransHubConfig` object and all its sub-configuration models, and explain how to customize the behavior of `Trans-Hub` using Python code, environment variables, or a `.env` file.

[Return to Document Index](../INDEX.md)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **1. Core Concept: `TransHubConfig`**

All configurations of `Trans-Hub` are managed by a core Pydantic model `TransHubConfig`. This is the "single source of truth" for all configurations. You should create an instance of `TransHubConfig` during your application initialization and pass it to the `Coordinator`.

Basic usage:

```python
from trans_hub.config import TransHubConfig

# Create a configuration object using all default settings
default_config = TransHubConfig()

# Create an object with a custom configuration
custom_config = TransHubConfig(
    active_engine="openai",
    source_lang="en",
    batch_size=100
)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

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

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **3. Sub-configuration Model**

`TransHubConfig` manages the behavior of different modules by combining multiple sub-configuration models. You can achieve deep customization by creating instances of the sub-models and passing them to `TransHubConfig`.

### **3.1 `cache_config: CacheConfig`**

Control the memory cache (L1 cache) behavior inside the `Coordinator`.

- **`maxsize`** (`int`): The maximum number of items that can be stored in the cache.
  - **Default value**: `1000`
- **`ttl`** (`int`): The lifespan of cache items (in seconds). Only effective when `cache_type="ttl"`.
  - **Default value**: `3600` (1 hour)
- **`cache_type`** (`str`): Cache strategy. Can be `"ttl"` (time-based expiration) or `"lru"` (least recently used eviction).
  - **Default value**: `"ttl"`

**Example**:

```python
from trans_hub.cache import CacheConfig

# Create an LRU cache configuration that can hold 10,000 items and has a validity period of 24 hours
custom_cache = CacheConfig(maxsize=10000, ttl=86400, cache_type="lru")

config = TransHubConfig(cache_config=custom_cache)

### **3.2 `retry_policy: RetryPolicyConfig`**

Define the retry strategy for `Coordinator` when encountering retryable errors.

- **`max_attempts`** (`int`): Maximum number of attempts (excluding the first call). `2` means a total of 3 attempts will be made.
  - **Default value**: `2`
- **`initial_backoff`** (`float`): Initial wait time before the first retry (seconds).
  - **Default value**: `1.0`
- **`max_backoff`** (`float`): Maximum wait time limit under exponential backoff strategy (seconds).
  - **Default value**: `60.0`

### **3.3 `logging: LoggingConfig`**

Configure the behavior of the `structlog` logging system.

- **`level`** (`str`): Log level, such as `"DEBUG"`, `"INFO"`, `"WARNING"`.
  - **Default value**: `"INFO"`
- **`format`** (`str`): Log output format. `"console"` is suitable for development environments (with color), while `"json"` is suitable for production environments.
  - **Default value**: `"console"`

### **3.4 `engine_configs: EngineConfigs`**

This is a special sub-model used to aggregate the configurations of all specific engines.

Usually, you do not need to manually create `EngineConfigs` instances. The smart validator of `TransHubConfig` will automatically create and populate it for you.

However, if you need to provide a specific startup configuration for a **non-active** engine (for example, to switch to it later using `switch_engine`), you can do so:

```python
from trans_hub.config import EngineConfigs
from trans_hub.engines.openai import OpenAIEngineConfig

# Manually provide a custom model for the OpenAI engine
openai_config = OpenAIEngineConfig(
    openai_model="gpt-4-turbo",
    # openai_api_key will be automatically loaded from .env
)

# Default activates translators, but also provides pre-configuration for openai
config = TransHubConfig(
    active_engine="translators",
    engine_configs=EngineConfigs(
        openai=openai_config
    )
)
```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

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
