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

- **零配置启动**: 内置基于 `translators` 库的免费翻译引擎，实现真正的“开箱即用”。
- **持久化缓存**: 所有翻译结果都会被自动存储在本地数据库（默认 SQLite）中。`Coordinator.process_pending_translations()` **只会处理待办（PENDING）或失败（FAILED）的任务**，对于已成功缓存的翻译，它不会重复处理，从而极大地降低了 API 调用成本和响应时间。
- **🔌 真正的插件化架构**:
  - **按需安装**: 核心库极其轻量。当你想使用更强大的引擎（如 OpenAI）时，只需安装其可选依赖即可。系统会自动检测并启用它们。
  - **轻松扩展**: 提供清晰的基类，可以方便地开发和接入自定义的翻译引擎。
- **健壮的错误处理**:
  - 内置可配置的**自动重试**机制，采用指数退避策略，从容应对临时的网络或 API 错误。
  - 在 API 入口处进行严格的参数校验，防止无效数据进入系统。
- **⚙️ 精准的策略控制**:
  - 内置**速率限制器**，保护你的 API 密钥不因请求过快而被服务商封禁。
  - 支持带**上下文（Context）**的翻译，实现对同一文本在不同场景下的不同译法。**上下文处理现在更精确，通过 `__GLOBAL__` 哨兵值确保数据库唯一性。**
- **生命周期管理**: 内置**垃圾回收（GC）**功能，可定期清理过时和不再使用的业务关联数据（`th_sources` 表中的 `last_seen_at` 字段）。
- **专业级可观测性**: 支持结构化的 JSON 日志和调用链 ID (`correlation_id`)。

## 🚀 快速上手：零配置体验

在短短几分钟内，体验 `Trans-Hub` 的强大功能，无需任何 API Key。

### 1. 安装

安装 `Trans-Hub` 核心库。它已经包含了运行免费翻译引擎所需的一切。

```bash
pip install trans-hub
```

### 2. 编写你的第一个翻译脚本

创建一个 Python 文件（例如 `quick_start.py`）。**你不需要创建 `.env` 文件或进行任何 API 配置！**

```python
# quick_start.py
import os
import structlog
from dotenv import load_dotenv

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler

# 获取一个 logger
log = structlog.get_logger()

def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    setup_logging(log_level="INFO")

    DB_FILE = "my_translations.db"

    # 在生产环境中，数据库迁移通常只在部署时执行一次。
    # 这里我们简化处理，如果数据库文件不存在，则创建并迁移。
    if not os.path.exists(DB_FILE):
        log.info("数据库不存在，正在创建并迁移...", db_path=DB_FILE)
        apply_migrations(DB_FILE)

    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 创建一个最简单的配置对象。
    # 它将自动使用默认的、免费的 'translators' 引擎。
    config = TransHubConfig()

    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

def main():
    """主程序入口"""
    # 在程序最开始主动加载 .env 文件，这是一个健壮的实践
    load_dotenv()

    coordinator = initialize_trans_hub()
    try:
        text_to_translate = "Hello, world!"
        target_language_code = "zh-CN"

        log.info("正在登记翻译任务", text=text_to_translate, lang=target_language_code)
        coordinator.request(
            target_langs=[target_language_code],
            text_content=text_to_translate,
            business_id="app.greeting.hello_world" # 关联一个业务ID
        )

        log.info(f"正在处理 '{target_language_code}' 的待翻译任务...")
        results = list(coordinator.process_pending_translations(
            target_lang=target_language_code
        ))

        if results:
            first_result = results[0]
            log.info(
                "翻译完成！",
                original=first_result.original_content,
                translation=first_result.translated_content,
                status=first_result.status.name,
                engine=first_result.engine,
                business_id=first_result.business_id # 显示关联的业务ID
            )
        else:
            log.warning("没有需要处理的新任务（可能已翻译过，这是缓存的体现）。")

    except Exception as e:
        log.critical("程序运行中发生未知严重错误！", exc_info=True)
    finally:
        if 'coordinator' in locals() and coordinator:
            coordinator.close()

if __name__ == "__main__":
    main()
```

### 3. 运行！

在你的终端中运行脚本：

```bash
python quick_start.py
```

第一次运行时，它会进行实际的翻译。

```
... [info     ] 数据库不存在，正在创建并迁移...
... [info     ] 正在登记翻译任务                       text=Hello, world! lang=zh-CN
... [info     ] 正在处理 'zh-CN' 的待翻译任务...
... [info     ] 翻译完成！                           original=Hello, world! translation=你好世界！ status=TRANSLATED engine=translators business_id=app.greeting.hello_world
```

再次运行 `python quick_start.py`（不删除数据库文件），你将看到 `Trans-Hub` 的缓存机制生效：

```
... [info     ] 正在登记翻译任务                       text=Hello, world! lang=zh-CN
... [info     ] 正在处理 'zh-CN' 的待翻译任务...
... [warning  ] 没有需要处理的新任务（可能已翻译过，这是缓存的体现）。
```

就是这么简单！`Trans-Hub` 自动为你处理了缓存。

---

## 升级到高级引擎 (例如 OpenAI)

当你需要更强大的翻译能力时，可以轻松升级。

**1. 安装可选依赖**:

```bash
pip install "trans-hub[openai]"
```

**2. 配置 `.env` 文件**:
在项目根目录创建 `.env` 文件。

```env
# .env
TH_OPENAI_ENDPOINT="https://api.openai.com/v1" # 例如，如果你使用 Azure OpenAI，需要修改此端点
TH_OPENAI_API_KEY="your-secret-key"
TH_OPENAI_MODEL="gpt-3.5-turbo" # 推荐使用 gpt-4 或其他更高级模型以获得更好质量
```

> 💡 查看 [`.env.example`](./.env.example) 获取所有可用配置。

**3. 在初始化时激活引擎**:
只需在创建配置时，明确指定 `active_engine` 即可。

```python
# 在你的初始化代码中
# ...
from trans_hub.config import EngineConfigs, TransHubConfig
from trans_hub.engines.openai import OpenAIEngineConfig

# ...

def initialize_trans_hub():
    # ... (与之前相同的初始化代码) ...
    handler = DefaultPersistenceHandler(db_path=DB_FILE)

    # 创建一个配置，并明确激活 'openai' 引擎
    config = TransHubConfig(
        active_engine="openai",
        engine_configs=EngineConfigs(
            openai=OpenAIEngineConfig() # 创建实例以触发 .env 加载和配置验证
        )
    )

    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

# ...
```

## 核心概念

- **Coordinator**: 你的主要交互对象，负责编排整个翻译流程。**它现在可以智能地驱动同步和异步两种引擎**，应用重试和速率限制，并协调业务信息以构建完整的 `TranslationResult`。
- **Engine**: 翻译服务的具体实现。`Trans-Hub` 会自动检测你安装了哪些引擎的依赖，并使其可用。
- **`request()`**: 用于“登记”一个翻译需求，非常轻量。它会更新 `th_sources` 表中对应 `business_id` 的活跃时间戳，并创建或更新 `th_translations` 表中的 `PENDING` 任务。
- **`process_pending_translations()`**: 用于“执行”翻译工作，会真实地调用 API，建议在后台执行。它只会处理状态为 `PENDING` 或 `FAILED` 的任务，并返回翻译结果。

## 深入了解

我们为您准备了详尽的文档库，覆盖了从快速入门到架构设计的方方面面。

### ➡️ [**探索官方文档中心 (Explore the Official Documentation Hub)**](./docs/INDEX.md)

在文档中心，您可以找到：

- **使用指南**: 循序渐进的教程，带您掌握高级功能。
- **API 参考**: 所有公共类和方法精确的定义。
- **架构文档**: 深入了解 `Trans-Hub` 的内部工作原理。
- **贡献指南**: 学习如何为项目贡献新的翻译引擎。

## 贡献

我们热烈欢迎任何形式的贡献！请先阅读我们的 **[贡献指南](./CONTRIBUTING.md)**。

## 行为准则

为了营造一个开放、友好的社区环境，请遵守我们的 **[行为准则](./CODE_OF_CONDUCT.md)**。

## 许可证

`Trans-Hub` 采用 [MIT 许可证](./LICENSE.md)。
