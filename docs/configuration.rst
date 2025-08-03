.. # docs/configuration.rst

==================
配置指南
==================

`Trans-Hub` 的所有行为都通过一个结构化的配置对象 ``TransHubConfig`` 进行控制。得益于 `pydantic-settings`，所有配置项都可以通过代码、环境变量或 `.env` 文件灵活设置。

配置加载顺序
------------

`Trans-Hub` 按照以下顺序加载配置（优先级从高到低，后加载的会覆盖先加载的）：

1. **代码中直接设置**：在 `TransHubConfig()` 初始化时传入的参数。
2. **环境变量**：系统中的环境变量（需以 `TH_` 为前缀）。
3. **`.env` 文件**：项目根目录下 `.env` 文件中定义的变量。
4. **模型定义的默认值**：在 `TransHubConfig` 及其子模型中定义的默认值。

核心配置对象
------------

核心配置对象是 :class:`~trans_hub.config.TransHubConfig`。

.. code-block:: python
   :caption: 在代码中进行基本配置

   from trans_hub.config import TransHubConfig

   config = TransHubConfig(
       active_engine="openai",
       database_url="sqlite:///./my_translations.db",
       source_lang="en"
   )

所有可用的配置参数都在 :class:`API 参考 <api/config>` 中有详细定义。以下是关键参数的说明。

关键配置参数
------------

### 通用配置

这些是 `TransHubConfig` 的顶层参数。

- ``active_engine`` (:class:`~trans_hub.config.EngineName`): **[必需]** 激活的翻译引擎名称。必须是 ``EngineName`` 枚举的成员之一。 (默认: ``"translators"``)
- ``database_url`` (`str`): **[必需]** 数据库连接字符串。目前只支持 SQLite。 (默认: ``"sqlite:///transhub.db"``)
- ``source_lang`` (`Optional[str]`): (可选) 全局默认的源语言代码。对于某些需要明确源语言的引擎（如 OpenAI），此项可能是必需的。 (默认: `None`)
- ``batch_size`` (`int`): 后台 Worker 处理任务时的默认批次大小。 (默认: 50)
- ``gc_retention_days`` (`int`): 垃圾回收（GC）时，保留最近多少天的活跃任务。 (默认: 90)

### 嵌套配置

更复杂的配置项被组织在嵌套的子模型中。

- ``retry_policy`` (:class:`~trans_hub.config.RetryPolicyConfig`): 配置后台 Worker 的重试策略。
  - ``max_attempts``: 最大尝试次数 (首次 + 重试)。 (默认: 2)
  - ``initial_backoff``: 初始退避时间（秒）。 (默认: 1.0)
  - ``max_backoff``: 最大退避时间（秒）。 (默认: 60.0)
- ``cache_config`` (:class:`~trans_hub.cache.CacheConfig`): 配置内存缓存。
  - ``maxsize``: 缓存的最大条目数。 (默认: 1000)
  - ``ttl``: 缓存项的存活时间（秒）。 (默认: 3600)
- ``logging`` (:class:`~trans_hub.config.LoggingConfig`): 配置日志系统。
  - ``level``: 日志级别，如 "INFO", "DEBUG"。 (默认: "INFO")
  - ``format``: 日志格式，"console" 或 "json"。 (默认: "console")
- ``engine_configs`` (:class:`~trans_hub.config.EngineConfigs`): **[重要]** 这是一个用于存放所有引擎特定配置的容器。

引擎特定配置
------------

所有引擎的特定配置都位于 ``engine_configs`` 对象内部。

.. code-block:: python
   :caption: 在代码中配置引擎特定参数

   from trans_hub.config import TransHubConfig
   from trans_hub.engines.openai import OpenAIEngineConfig

   config = TransHubConfig(
       active_engine="openai",
       engine_configs={
           "openai": OpenAIEngineConfig(
               openai_api_key="sk-...",
               openai_model="gpt-4o"
           )
       }
   )

.. note::
   您**只需**为您计划使用的引擎提供配置。

- **OpenAI 引擎** (:class:`~trans_hub.engines.openai.OpenAIEngineConfig`)
  - ``openai_api_key``: 您的 OpenAI API 密钥。
  - ``openai_model``: 使用的模型，如 "gpt-3.5-turbo", "gpt-4o"。
  - ``openai_endpoint``: (可选) 用于代理或兼容其他 OpenAI API 的端点 URL。
- **Translators 引擎** (:class:`~trans_hub.engines.translators_engine.TranslatorsEngineConfig`)
  - ``provider``: 使用的免费翻译服务提供商，如 "google", "bing"。
- **Debug 引擎** (:class:`~trans_hub.engines.debug.DebugEngineConfig`)
  - ``mode``: "SUCCESS" 或 "FAIL"，用于模拟成功或失败场景。

通过环境变量或 `.env` 文件配置
--------------------------------

这是在生产环境中配置 `Trans-Hub` 的**推荐方式**。`pydantic-settings` 会自动读取环境变量或 `.env` 文件，并将其映射到配置对象。

**映射规则**:
- **前缀**: 所有环境变量都必须以 `TH_` 开头。
- **嵌套**: 使用双下划线 `__` 来表示配置的嵌套层级。
- **大小写**: 环境变量不区分大小写。

**示例 `.env` 文件**:

.. code-block:: shell
   :caption: .env

   # --- 通用配置 ---
   TH_ACTIVE_ENGINE="openai"
   TH_DATABASE_URL="sqlite:///./prod.db"
   TH_SOURCE_LANG="en"
   
   # --- 嵌套配置：日志 ---
   TH_LOGGING__LEVEL="DEBUG"

   # --- 嵌套配置：OpenAI 引擎 ---
   TH_ENGINE_CONFIGS__OPENAI__OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   TH_ENGINE_CONFIGS__OPENAI__OPENAI_MODEL="gpt-4o"
   TH_ENGINE_CONFIGS__OPENAI__RPM=2500 # 每分钟请求数限制

配置验证
--------

`TransHubConfig` 及其所有子模型都基于 Pydantic 构建，这意味着所有配置在加载时都会被严格验证。如果提供了无效的类型或缺失必需的配置（例如为 `openai` 引擎但未提供 API key），程序将在启动时立即抛出 `ValidationError`，从而实现“快速失败”，避免在运行时出现意外。