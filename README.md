# Trans-Hub: 智能本地化后端引擎 🚀

[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)  <!-- 当你发布到PyPI后，这个徽章会生效 -->
[![Python versions](https://img.shields.io/pypi/pyversions/trans-hub.svg)](https://pypi.org/project/trans-hub) <!-- PyPI会自动检测支持的Python版本 -->
[![CI/CD Status](https://github.com/your-username/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/trans-hub/actions) <!-- 将 your-username/trans-hub 替换为你的GitHub路径 -->
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`Trans-Hub` 是一个可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。**

它旨在统一和简化多语言翻译工作流，通过**智能缓存、插件化翻译引擎、自动重试和速率限制**，为你的应用提供高效、低成本、高可靠的翻译能力。无论你是在开发一个需要多语言支持的Web应用、桌面软件，还是需要批量翻译结构化数据，`Trans-Hub`都能成为你强大的后端。

---

## ✨ 核心特性

*   **持久化缓存**: 所有翻译请求和结果都会被自动存储在本地数据库（默认SQLite）中。重复的翻译请求会立即从缓存返回，极大地降低了API调用成本和响应时间。
*   **🔌 插件化翻译引擎**:
    *   轻松集成不同的翻译服务（如 OpenAI, DeepL, Google Translate等）。
    *   提供清晰的基类，可以方便地开发和接入自定义的翻译引擎。
*   **健壮的错误处理**:
    *   内置可配置的**自动重试**机制，采用指数退避策略，从容应对临时的网络或API错误。
    *   智能区分可重试（如 `503 Service Unavailable`）和不可重试（如 `401 Unauthorized`）的错误。
*   **⚙️ 精准的策略控制**:
    *   内置**速率限制器**，保护你的API密钥不因请求过快而被服务商封禁。
    *   支持带**上下文（Context）**的翻译，实现对同一文本在不同场景下的不同译法。
*   **生命周期管理**: 内置**垃圾回收（GC）**功能，可定期清理过时和不再使用的数据，保持数据库健康。
*   **专业级可观测性**: 支持结构化的 JSON 日志和调用链 ID (`correlation_id`)，便于在生产环境中进行监控和问题排查。

##  Quickstart: 快速上手

在短短几分钟内，体验 `Trans-Hub` 的强大功能。

### 1. 安装

首先，安装 `Trans-Hub` 核心库。如果你需要使用 OpenAI 引擎，请同时安装 `openai` extra。

```bash
# 安装核心库和 OpenAI 引擎
poetry add trans-hub -E openai

# 或者使用 pip
pip install "trans-hub[openai]"
```

### 2. 配置你的 `.env` 文件

在你的项目根目录下创建一个 `.env` 文件，并填入你的翻译引擎配置。

```env
# .env

# --- OpenAI 引擎配置 ---
# 你的API地址
TH_OPENAI_ENDPOINT="https://api.openai.com/v1"

# 你的API密钥
TH_OPENAI_API_KEY="your-secret-key"

# 你希望使用的模型
TH_OPENAI_MODEL="gpt-3.5-turbo"
```

### 3. 编写你的第一个翻译脚本

创建一个 Python 文件（例如 `main.py`），然后编写以下代码：

```python
import os
from dotenv import load_dotenv

# 导入 Trans-Hub 的核心组件
from trans_hub.coordinator import Coordinator
from trans_hub.db.schema_manager import apply_migrations
from trans_hub.engines.openai import OpenAIEngine, OpenAIEngineConfig
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.logging_config import setup_logging

def run_translation():
    # 1. 在程序入口主动加载 .env 文件，这是最佳实践
    load_dotenv()
    
    # 2. 配置日志系统
    setup_logging(log_level="INFO", log_format="console")

    # 3. 准备数据库
    DB_FILE = "my_translations.db"
    # 如果是第一次运行，执行数据库迁移
    if not os.path.exists(DB_FILE):
        print(f"数据库 '{DB_FILE}' 不存在，正在创建并迁移...")
        apply_migrations(DB_FILE)

    # 4. 初始化所有组件
    # 持久化处理器，负责与数据库交互
    handler = DefaultPersistenceHandler(db_path=DB_FILE)
    
    # 创建并配置 OpenAI 引擎（它会自动从 .env 读取配置）
    try:
        openai_config = OpenAIEngineConfig()
        openai_engine = OpenAIEngine(config=openai_config)
    except ValueError as e:
        print(f"配置错误: {e}")
        return

    # 将所有引擎实例放入字典
    engines = {"openai": openai_engine}

    # 初始化主协调器，它是你与 Trans-Hub 交互的主要入口
    coordinator = Coordinator(
        persistence_handler=handler,
        engines=engines,
        active_engine_name="openai" # 指定当前使用哪个引擎
    )

    try:
        # --- 开始使用 Trans-Hub ---

        # 5. 发起翻译请求
        # 这是一个异步登记操作，它会很快返回
        print("\n>> 正在登记翻译任务...")
        coordinator.request(
            target_langs=['French', 'Japanese'],
            text_content="Welcome to the future of translation.",
            business_id="ui.homepage.welcome_banner"
        )
        coordinator.request(
            target_langs=['Japanese'],
            text_content="Settings",
            business_id="ui.menu.settings"
        )

        # 6. 处理待办的翻译任务
        # 这通常在一个后台任务或定时脚本中执行
        print("\n>> 正在处理 'Japanese' 的待翻译任务...")
        jp_results = coordinator.process_pending_translations(target_lang='Japanese')
        
        # 实时获取翻译结果
        for result in jp_results:
            print(f"  实时结果: {result.original_content} -> {result.translated_content} ({result.status})")

        print("\n所有日语任务处理完毕！")
        
    finally:
        # 7. 优雅地关闭资源
        coordinator.close()

if __name__ == "__main__":
    run_translation()
```

### 4. 运行！

在你的终端中运行脚本：
```bash
python main.py
```

你将会看到 `Trans-Hub` 创建数据库、登记任务、调用 OpenAI API，并打印出实时的翻译结果！如果你再次运行该脚本，第二次处理任务时它会变得更快，因为部分结果可能已经存在于缓存中（尽管我们的示例没有重复请求）。

## 核心概念

*   **Coordinator**: 你的主要交互对象，负责编排整个翻译流程。
*   **PersistenceHandler**: 数据库的守护者，负责所有数据的存取。
*   **Engine**: 翻译服务的具体实现，例如 `OpenAIEngine`。
*   **`request()`**: 用于“登记”一个翻译需求。你可以频繁地调用它，它非常轻量。
*   **`process_pending_translations()`**: 用于“执行”翻译工作。这是一个重量级操作，会真实地调用API，建议在后台执行。

## 深入了解

想要了解更多关于 `Trans-Hub` 的设计哲学、`business_id` 的命名规范或如何开发自己的翻译引擎吗？请参考我们的 [**完整技术开发文档**](link-to-your-full-documentation.md)。 <!-- 这里可以链接到你更详细的文档 -->

## 贡献

我们欢迎任何形式的贡献！无论是提交 Bug 报告、功能建议还是代码 Pull Request。请先阅读我们的贡献指南（`CONTRIBUTING.md`）。

## 许可证

`Trans-Hub` 采用 [MIT 许可证](LICENSE.md)。