# 指南 3：配置深度解析

欢迎来到 `Trans-Hub` 的配置深度解析指南。本文档将详尽地介绍 `TransHubConfig` 对象及其所有子配置模型，并解释如何通过 Python 代码、环境变量或 `.env` 文件来定制 `Trans-Hub` 的行为。

[返回文档索引](../INDEX.md)

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

## **2. 顶层配置参数**

这些参数可以直接在 `TransHubConfig` 初始化时设置。

- **`database_url`** (`str`)

  - **描述**: 指定 `Trans-Hub` 使用的数据库的连接字符串。
  - **默认值**: `"sqlite:///transhub.db"`
  - **示例**:

    ```python
    # 使用一个位于 /var/data/ 的持久化数据库文件
    config = TransHubConfig(database_url="sqlite:////var/data/my_app_translations.db")

    # 使用内存数据库（仅用于测试，数据不会持久化）
    config = TransHubConfig(database_url="sqlite:///:memory:")
    ```

- **`active_engine`** (`str`)

  - **描述**: 指定 `Coordinator` 在启动时默认激活的翻译引擎。这个值必须与 `trans_hub/engines` 目录下某个引擎的注册名（通常是文件名）相匹配。
  - **默认值**: `"translators"`
  - **示例**: `TransHubConfig(active_engine="openai")`

- **`batch_size`** (`int`)

  - **描述**: 在 `process_pending_translations` 工作流中，每次从数据库获取待办任务批次的大小。
  - **默认值**: `50`
  - **注意**: 最终的批次大小还会受到引擎自身 `max_batch_size` 的限制。

- **`source_lang`** (`Optional[str]`)

  - **描述**: 全局默认的源语言代码（例如 `"en"`, `"zh"`）。对于那些需要明确源语言的引擎（如 `OpenAIEngine`），此配置非常重要。
  - **默认值**: `None`

- **`gc_retention_days`** (`int`)
  - **描述**: 垃圾回收（GC）的默认数据保留期限（天）。`run_garbage_collection` 在未指定 `expiration_days` 参数时会使用此值。
  - **默认值**: `90`

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

## **4. 通过环境变量和 `.env` 文件配置**

`Trans-Hub` 广泛使用 `pydantic-settings`，这意味着许多配置（特别是那些继承自 `BaseSettings` 的引擎配置）都可以通过环境变量或项目根目录下的 `.env` 文件来设置。

### **命名约定**

环境变量的名称由**前缀** + **配置路径**构成。

- **默认前缀**: `TH_` (用于 `OpenAIEngineConfig` 等)
- **配置路径**: 字段名通过下划线 `_` 连接。

### **示例**

假设你想覆盖 `OpenAIEngine` 的 `openai_model` 和 `temperature`。

**在 `.env` 文件中**:

```dotenv
# .env
TH_OPENAI_API_KEY="sk-..."
TH_OPENAI_MODEL="gpt-4-turbo"
TH_OPENAI_TEMPERATURE="0.5"
```

当你的应用创建 `TransHubConfig(active_engine="openai")` 时，`OpenAIEngineConfig` 实例会自动读取这些值。

### **优先级顺序**

Pydantic Settings 的配置加载遵循以下优先级顺序（从高到低）：

1.  **直接在代码中初始化的参数** (例如 `OpenAIEngineConfig(openai_model="...")`)
2.  **环境变量** (例如 `export TH_OPENAI_MODEL="..."`)
3.  **`.env` 文件中的值**
4.  **配置模型中定义的默认值**

这为你提供了极大的灵活性，可以在不同环境中（开发、测试、生产）使用不同的配置，而无需修改任何代码。
