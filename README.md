# Trans-Hub: 智能本地化后端引擎 🚀

[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![Python versions](https://img.shields.io/pypi/pyversions/trans-hub.svg)](https://pypi.org/project/trans-hub)
[![CI/CD Status](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`Trans-Hub` 是一个可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。**

它旨在统一和简化多语言翻译工作流，通过**智能缓存、插件化翻译引擎、自动重试和速率限制**，为你的应用提供高效、低成本、高可靠的翻译能力。无论你是在开发一个需要多语言支持的Web应用、桌面软件，还是需要批量翻译结构化数据，`Trans-Hub`都能成为你强大的后端。

---

## ✨ 核心特性

*   **持久化缓存**: 所有翻译请求和结果都会被自动存储在本地数据库（默认SQLite）中。重复的翻译请求会立即从缓存返回，极大地降低了API调用成本和响应时间。
*   **🔌 真正的插件化架构**:
    *   **按需安装**: 核心库极其轻量。你只需安装你真正需要的翻译引擎依赖，系统会自动检测并启用它们。
    *   **轻松扩展**: 提供清晰的基类，可以方便地开发和接入自定义的翻译引擎。
*   **健壮的错误处理**:
    *   内置可配置的**自动重试**机制，采用指数退避策略，从容应对临时的网络或API错误。
    *   智能区分可重试（如 `503 Service Unavailable`）和不可重试（如 `401 Unauthorized`）的错误。
*   **⚙️ 精准的策略控制**:
    *   内置**速率限制器**，保护你的API密钥不因请求过快而被服务商封禁。
    *   支持带**上下文（Context）**的翻译，实现对同一文本在不同场景下的不同译法。
*   **生命周期管理**: 内置**垃圾回收（GC）**功能，可定期清理过时和不再使用的数据，保持数据库健康。
*   **专业级可观测性**: 支持结构化的 JSON 日志和调用链 ID (`correlation_id`)，便于在生产环境中进行监控和问题排查。

## 🚀 快速上手

在短短几分钟内，体验 `Trans-Hub` 的强大功能。

### 1. 安装

`Trans-Hub` 的安装非常灵活。你可以只安装核心库，也可以根据需要一并安装特定翻译引擎的依赖。

```bash
# 方案一：只安装核心库 (非常轻量)
pip install trans-hub

# 方案二（推荐）：安装核心库，并附带 OpenAI 引擎所需的依赖
pip install "trans-hub[openai]"

# 方案三：安装所有官方支持的引擎依赖 (未来)
# pip install "trans-hub[all]"
```
*我们推荐使用方案二开始。*

### 2. 配置你的 `.env` 文件

在你的项目根目录下创建一个 `.env` 文件，并填入你的翻译引擎配置。`Trans-Hub` 会自动加载这些配置。

```env
# .env.example - 请复制为 .env 并修改

# --- OpenAI 引擎配置 ---
# 我们使用 ENDPOINT 是为了避免潜在的解析问题
TH_OPENAI_ENDPOINT="https://your-api-endpoint.com/v1"
TH_OPENAI_API_KEY="your-secret-key"
TH_OPENAI_MODEL="gpt-3.5-turbo"
```
> 💡 查看 [`.env.example`](./.env.example) 文件获取所有可用的配置选项。

### 3. 编写你的第一个翻译脚本

创建一个 Python 文件（例如 `main.py`），然后编写以下代码：

```python
import os
from dotenv import load_dotenv

# 导入 Trans-Hub 的核心组件
from trans_hub.config import TransHubConfig, EngineConfigs
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.openai import OpenAIEngineConfig # 只导入你需要的配置
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

def initialize_trans_hub():
    """一个标准的初始化函数，返回一个配置好的 Coordinator 实例。"""
    # 1. 在程序入口主动加载 .env 文件，这是最健壮的方式
    load_dotenv()
    setup_logging(log_level="INFO")

    # 2. 准备数据库
    DB_FILE = "my_translations.db"
    if not os.path.exists(DB_FILE):
        print(f"数据库 '{DB_FILE}' 不存在，正在创建并迁移...")
        apply_migrations(DB_FILE)
    
    # 3. 初始化持久化处理器和配置对象
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    # Trans-Hub 会自动从 .env 加载配置，我们只需构建总配置对象
    config = TransHubConfig(
        database_url=f"sqlite:///{DB_FILE}",
        active_engine="openai", # 指定要使用的引擎
        engine_configs=EngineConfigs(
            openai=OpenAIEngineConfig() # 创建一个实例以触发加载
        )
    )
    
    # 4. 初始化主协调器
    coordinator = Coordinator(config=config, persistence_handler=handler)
    return coordinator

def main():
    coordinator = initialize_trans_hub()

    try:
        # --- 开始使用 Trans-Hub ---

        # 步骤 1: 登记翻译需求 (这是一个轻量级操作)
        print("\n>> 正在登记翻译任务...")
        coordinator.request(
            target_langs=['French', 'Japanese'],
            text_content="Welcome to the future of translation.",
            business_id="ui.homepage.welcome_banner"
        )

        # 步骤 2: 执行翻译工作 (这是一个重量级操作，会调用API)
        # 建议在后台任务或定时脚本中执行
        print("\n>> 正在处理 'Japanese' 的待翻译任务...")
        jp_results = coordinator.process_pending_translations(target_lang='Japanese')
        
        # 你可以实时获取和处理结果
        for result in jp_results:
            print(f"  实时结果: {result.original_content} -> {result.translated_content} ({result.status})")

        print("\n所有日语任务处理完毕！")
        
    finally:
        # 优雅地关闭数据库连接等资源
        coordinator.close()

if __name__ == "__main__":
    main()
```

### 4. 运行！

在你的终端中运行脚本：
```bash
python main.py
```

你将会看到 `Trans-Hub` 创建数据库、登记任务、调用 OpenAI API，并打印出实时的翻译结果！如果你再次运行该脚本，由于缓存的存在，它会跳过已翻译的任务，变得更快。

## 核心概念

*   **Coordinator**: 你的主要交互对象，负责编排整个翻译流程。
*   **PersistenceHandler**: 数据库的守护者，负责所有数据的存取。
*   **Engine**: 翻译服务的具体实现。`Trans-Hub` 会自动检测你安装了哪些引擎的依赖，并使其可用。
*   **`request()`**: 用于“登记”一个翻译需求。你可以频繁地调用它，它非常轻量。
*   **`process_pending_translations()`**: 用于“执行”翻译工作。这是一个重量级操作，会真实地调用API，建议在后台执行。

## 深入了解

*   想要在 Flask/Django 中使用？请查看我们的 **[Cookbook](./docs/cookbook.md)**。
*   想开发自己的翻译引擎？请阅读 **[第三方引擎开发指南](./docs/developing-engines.md)**。
*   对项目的设计哲学和内部架构感兴趣？请深入我们的 **[技术规范文档](./docs/technical-specification-v1.md)**。

## 贡献

我们热烈欢迎任何形式的贡献！无论是提交 Bug 报告、功能建议还是代码 Pull Request。请先阅读我们的贡献指南（`CONTRIBUTING.md`）。

## 许可证

`Trans-Hub` 采用 [MIT 许可证](./LICENSE.md)。