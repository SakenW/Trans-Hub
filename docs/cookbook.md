# Trans-Hub: 智能本地化后端引擎 🚀

[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![Python versions](https://img.shields.io/pypi/pyversions/trans-hub.svg)](https://pypi.org/project/trans-hub)
[![CI/CD Status](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`Trans-Hub` 是一个可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。**

它旨在统一和简化多语言翻译工作流，通过**智能缓存、插件化翻译引擎、自动重试和速率限制**，为你的应用提供高效、低成本、高可靠的翻译能力。

最棒的是，`Trans-Hub` **开箱即用**！内置强大的免费翻译引擎，让你无需任何 API Key 或复杂配置，即可在几分钟内开始翻译。

---

## ✨ 核心特性

*   **零配置启动**: 内置基于 `translators` 库的免费翻译引擎，实现真正的“开箱即用”。
*   **持久化缓存**: 所有翻译结果都会被自动存储在本地数据库（默认SQLite）中。重复的翻译请求会立即从缓存返回，极大地降低了API调用成本和响应时间。
*   **🔌 真正的插件化架构**:
    *   **按需安装**: 核心库极其轻量。当你想使用更强大的引擎（如 OpenAI）时，只需安装其可选依赖即可。系统会自动检测并启用它们。
    *   **轻松扩展**: 提供清晰的基类和开发指南，可以方便地开发和接入自定义的翻译引擎。
*   **健壮的错误处理**:
    *   内置可配置的**自动重试**机制，采用指数退避策略，从容应对临时的网络或API错误。
    *   在 API 入口处进行严格的参数校验，防止无效数据进入系统。
*   **⚙️ 精准的策略控制**:
    *   内置**速率限制器**，保护你的API密钥不因请求过快而被服务商封禁。
    *   支持带**上下文（Context）**的翻译，实现对同一文本在不同场景下的不同译法。
*   **生命周期管理**: 内置**垃圾回收（GC）**功能，可定期清理数据库中过时和不再被引用的数据。
*   **专业级可观测性**: 支持结构化的 JSON 日志和调用链 ID (`correlation_id`)，便于日志分析和问题追踪。

## 🚀 快速上手：零配置体验

在短短几分钟内，体验 `Trans-Hub` 的强大功能，无需任何 API Key。

### 1. 安装

安装 `Trans-Hub` 核心库。它已经包含了运行免费翻译引擎所需的一切。

```bash
pip install trans-hub
```

### 2. 编写你的第一个翻译脚本

创建一个 Python 文件（例如 `main.py`）。**你不需要创建 `.env` 文件或进行任何 API 配置！**

```python
# main.py
import os
import sys
import structlog # 导入 structlog
import dotenv # 导入 dotenv 库

# 导入 Trans-Hub 的核心组件
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging # 导入日志配置函数
from trans_hub.types import TranslationStatus # 导入 TranslationStatus 枚举

# 获取一个模块级别的日志记录器，与项目其他文件保持一致
log = structlog.get_logger(__name__)

def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    # 日志系统初始化：建议在应用程序启动时尽早调用
    # 在快速上手示例中，'console' 格式更便于开发时阅读
    setup_logging(log_level="INFO", log_format="console") 

    DB_FILE = "my_translations.db"
    # 检查数据库文件是否存在，如果不存在则创建并应用迁移
    if not os.path.exists(DB_FILE):
        log.info("数据库文件不存在，正在创建并应用迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)
    
    # 初始化持久化处理器，负责数据库交互
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    # 创建 TransHubConfig 对象。
    # 如果没有在 .env 中指定 active_engine，TransHub 会默认使用内置的 'translators' 引擎。
    # EngineConfigs() 不带参数则表示使用默认的引擎配置。
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        engine_configs=EngineConfigs() # 默认使用 translators 引擎的配置
    )
    
    # 初始化协调器，它是 Trans-Hub 的核心入口
    coordinator = Coordinator(config=config, persistence_handler=handler)
    log.info("Trans-Hub 协调器初始化成功。")
    return coordinator

def main():
    """主程序入口"""
    # 在程序最开始主动加载 .env 文件，这是一个健壮的实践。
    # 即使在本零配置示例中没有 .env 文件，调用它也无害，并为升级到高级引擎做准备。
    dotenv.load_dotenv() 
    
    coordinator = None # 初始化为 None，以便在 finally 块中安全检查
    try:
        coordinator = initialize_trans_hub()
        text_to_translate = "Hello, world!"
        # 使用标准的 IETF 语言标签 (例如 'en', 'zh-CN', 'ja')
        target_language_code = "zh-CN"

        # --- 使用 try...except 块来优雅地处理预期的错误 ---
        try:
            log.info("正在登记翻译任务", text=text_to_translate, target_lang=target_language_code)
            coordinator.request(
                target_langs=[target_language_code],
                text_content=text_to_translate,
                business_id="app.greeting.hello_world" # 为翻译内容指定业务ID
            )
            log.info("翻译任务登记完成。")
        except ValueError as e:
            # 捕获我们自己定义的输入验证错误（例如语言代码格式错误）
            log.error(
                "无法登记翻译任务，输入参数有误。",
                reason=str(e),
                suggestion="请检查你的语言代码是否符合 'en' 或 'zh-CN' 这样的标准格式。",
                exc_info=True # 打印完整的异常信息
            )
            # 优雅地退出程序，退出代码为 1 表示有错误发生
            sys.exit(1)

        # --- 执行翻译工作 ---
        log.info(f"正在处理 '{target_language_code}' 的待翻译任务...")
        # process_pending_translations 返回一个生成器，逐个处理并返回结果
        results_generator = coordinator.process_pending_translations(
            target_lang=target_language_code
        )
        
        # 将生成器结果转换为列表，以便后续检查
        results = list(results_generator)
        
        if results:
            first_result = results[0]
            log.info(
                "翻译完成！",
                original=first_result.original_content,
                translation=first_result.translated_content,
                status=first_result.status.value, # 打印枚举的字符串值
                engine=first_result.engine
            )
            # 进一步检查翻译状态
            if first_result.status == TranslationStatus.TRANSLATED:
                 log.info("翻译任务成功完成。")
            else:
                 log.warning(f"翻译任务状态为: {first_result.status.value} (可能失败或仍在处理中)。")
        else:
            log.warning("没有需要处理的新任务（可能所有任务都已在数据库中）。")

    except Exception as e:
        # 捕获所有其他意外的、严重的错误
        log.critical("程序运行中发生未知严重错误！", error=str(e), exc_info=True)
        sys.exit(1) # 严重错误也应退出程序
    finally:
        # 确保 coordinator 实例存在时才调用 close，释放资源
        if coordinator: 
            log.info("关闭 Trans-Hub 协调器...")
            coordinator.close()
            log.info("Trans-Hub 协调器已关闭。")

if __name__ == "__main__":
    main()
```

### 3. 运行！

在你的终端中运行脚本：
```bash
python main.py
```

你将会看到类似下面这样的输出，清晰地展示了从原文到译文的整个过程：

```
2024-06-12T... [info     ] 数据库文件不存在，正在创建并应用迁移... db_path=my_translations.db
2024-06-12T... [info     ] Trans-Hub 协调器初始化成功。
2024-06-12T... [info     ] 正在登记翻译任务                     text=Hello, world! target_lang=zh-CN
2024-06-12T... [info     ] 翻译任务登记完成。
2024-06-12T... [info     ] 正在处理 'zh-CN' 的待翻译任务...
2024-06-12T... [info     ] 翻译完成！                           original=Hello, world! translation=你好，世界！ status=TRANSLATED engine=translators
2024-06-12T... [info     ] 翻译任务成功完成。
2024-06-12T... [info     ] 关闭 Trans-Hub 协调器...
2024-06-12T... [info     ] Trans-Hub 协调器已关闭。
```
就是这么简单！你已经成功地使用 `Trans-Hub` 完成了你的第一个翻译任务。

---

## 升级到高级引擎 (例如 OpenAI)

当你需要更强大的翻译能力时，可以轻松升级。

**1. 安装可选依赖**:
```bash
pip install "trans-hub[openai]"
```

**2. 配置 `.env` 文件**:
在项目根目录创建 `.env` 文件，并填写你的 OpenAI API 凭证。
```env
# .env
TH_OPENAI_ENDPOINT="https://api.openai.com/v1" # OpenAI API 的默认端点
TH_OPENAI_API_KEY="your-secret-key" # 你的 OpenAI API Key
TH_OPENAI_MODEL="gpt-3.5-turbo" # 你想使用的 OpenAI 模型，例如 gpt-4o 或 gpt-3.5-turbo
```
> 💡 查看 [`.env.example`](./.env.example) 获取所有可用配置的完整示例。

**3. 在初始化时激活引擎**:
只需在创建 `TransHubConfig` 时，明确指定 `active_engine` 为 `"openai"`，并在 `engine_configs` 中传入 `OpenAIEngineConfig` 的实例即可。`pydantic-settings` 会自动从环境变量中加载 `api_key` 和 `base_url`。

```python
# 在你的初始化代码中 (例如 initialize_trans_hub 函数内)
import os
import structlog
from dotenv import load_dotenv # 确保导入
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging
from trans_hub.engines.openai import OpenAIEngineConfig # 导入 OpenAI 引擎配置

log = structlog.get_logger(__name__)

def initialize_trans_hub_with_openai():
    load_dotenv() # 加载 .env 文件
    setup_logging(log_level="INFO", log_format="console")

    DB_FILE = "my_openai_translations.db"
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)
    
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    # 核心：指定 active_engine 为 "openai"，并提供 OpenAIEngineConfig 实例
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        active_engine="openai",  
        engine_configs=EngineConfigs(
            # 创建 OpenAIEngineConfig 实例，它将自动从 .env 文件中加载配置
            openai=OpenAIEngineConfig() 
        )
    )
    
    coordinator = Coordinator(config=config, persistence_handler=handler)
    log.info("Trans-Hub 协调器初始化成功，使用 OpenAI 引擎。")
    return coordinator

# ... 然后在 main 函数中调用 initialize_trans_hub_with_openai()
# ... 并像之前一样调用 coordinator.request() 和 process_pending_translations()
```

## 核心概念

*   **Coordinator**: 你与 `Trans-Hub` 交互的主要对象，负责编排整个翻译流程，包括任务登记、执行、重试、速率限制和垃圾回收。
*   **Engine**: 翻译服务的具体实现，例如 `OpenAIEngine` 或 `TranslatorsEngine`。`Trans-Hub` 会自动检测你安装了哪些引擎的依赖，并使其可用。
*   **`request()`**: 用于“登记”一个翻译需求到数据库中。这是一个轻量级操作，仅记录待办任务，不立即执行翻译。
*   **`process_pending_translations()`**: 用于“执行”实际的翻译工作。它会从数据库中获取待办任务，调用活动引擎 API 进行翻译，并将结果保存回数据库。此方法可能会触发外部 API 调用，建议在后台工作者（如 Celery、RQ）中异步执行。

## 深入了解

*   想要在 Flask/Django 等 Web 框架中使用？请查看我们的 **[Cookbook](./docs/cookbook.md)** 获取更多实用范例。
*   想开发自己的翻译引擎？请阅读 **[第三方引擎开发指南](./docs/developing-engines.md)**。
*   对项目的设计哲学和内部架构感兴趣？请深入我们的 **[项目技术规范文档](./docs/technical-specification-v1.md)**。

## 贡献

我们热烈欢迎任何形式的贡献！请先阅读我们的 **[贡献指南](./CONTRIBUTING.md)**。

## 行为准则

为了营造一个开放、友好的社区环境，请遵守我们的 **[行为准则](./CODE_OF_CONDUCT.md)**。

## 许可证

`Trans-Hub` 采用 [MIT 许可证](./LICENSE.md)。

---