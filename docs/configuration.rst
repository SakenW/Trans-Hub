.. # docs/configuration.rst

==================
配置指南
==================

`Trans-Hub` 的所有行为都通过一个结构化的配置对象 ``TransHubConfig`` 进行控制。得益于 `pydantic-settings`，所有配置项都可以通过代码、环境变量或 `.env` 文件灵活设置。

配置加载顺序
------------

`Trans-Hub` 按照以下顺序加载配置（优先级从高到低）：

1.  代码中直接设置
2.  环境变量 (以 `TH_` 为前缀)
3.  `.env` 文件
4.  模型定义的默认值

核心配置对象
------------

核心配置对象是 :class:`~trans_hub.config.TransHubConfig`。所有可用参数请参阅 :doc:`api/config`。

关键配置参数
------------

### 通用配置

- ``active_engine`` (`str`): 激活的翻译引擎名称。 (默认: ``"translators"``)
- ``database_url`` (`str`): 数据库连接字符串。 (默认: ``"sqlite:///transhub.db"``)
- ``source_lang`` (`Optional[str]`): 全局默认的源语言代码。
- ``engine_configs`` (`Dict[str, Any]`): **[重要]** 一个用于存放所有引擎特定配置的**通用字典**。

### 嵌套配置

- ``retry_policy``: 配置后台 Worker 的重试策略。
- ``cache_config``: 配置内存缓存。
- ``logging``: 配置日志系统。

引擎特定配置
------------

所有引擎的特定配置都通过向 ``engine_configs`` 字典添加一个键值对来完成，键是引擎的名称。

.. code-block:: python
   :caption: 在代码中配置引擎特定参数

   from trans_hub.config import TransHubConfig

   config = TransHubConfig(
       active_engine="openai",
       engine_configs={
           "openai": {
               "api_key": "sk-...", # 将会被 OpenAIEngineConfig 解析
               "model": "gpt-4o"
           }
       }
   )

`Trans-Hub` 会在运行时使用引擎自身的配置模型（如 `OpenAIEngineConfig`）来动态解析和验证这些字典。

通过环境变量或 `.env` 文件配置
--------------------------------

这是在生产环境中配置 `Trans-Hub` 的**推荐方式**。

**映射规则**:
- **前缀**: 环境变量以 `TH_` 开头。
- **嵌套**: 使用双下划线 `__` 表示配置的嵌套层级。

**示例 `.env` 文件**:

.. code-block:: shell
   :caption: .env

   # --- 通用配置 ---
   TH_ACTIVE_ENGINE="openai"
   TH_DATABASE_URL="sqlite:///./prod.db"
   TH_SOURCE_LANG="en"
   
   # --- 嵌套配置：日志 ---
   TH_LOGGING__LEVEL="DEBUG"

   # --- 引擎配置 (简单值) ---
   # 注意: pydantic-settings 不直接支持从 env 加载复杂字典。
   # 对于 API Key 等简单值，我们为最常用的引擎提供了别名。
   TH_OPENAI_API_KEY="sk-xxxxxxxxxx"

配置验证
--------

所有配置在加载时都会被 Pydantic 严格验证，实现“快速失败”。