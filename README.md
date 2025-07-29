<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->
<details open>
<summary><strong>English</strong></summary>

# **Trans-Hub: Your Asynchronous Localization Backend Engine** 🚀

</details>

<details>
<summary><strong>简体中文</strong></summary>

# **Trans-Hub：您的异步本地化后端引擎** 🚀

</details>

[![Python CI/CD Pipeline](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/SakenW/trans-hub/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/SakenW/trans-hub)
[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<details open>
<summary><strong>English</strong></summary>

A Python-designed embeddable asynchronous localization engine specifically for automating dynamic content translation.

Trans-Hub is an **asynchronous-first**, embeddable Python application with persistent storage, serving as an intelligent localization (i18n) backend engine. It aims to unify and simplify multilingual translation workflows, providing efficient, low-cost, and highly reliable translation capabilities for upper-layer applications through intelligent caching, pluggable translation engines, and robust error handling and policy control.

## **Core Features**

- **Pure Asynchronous Design**: Built on `asyncio`, perfectly integrates with modern Python web frameworks like FastAPI and Starlette.
- **Persistent Caching**: All translation requests and results are automatically stored in an SQLite database, avoiding duplicate translations and saving costs.
- **Plugin-based Translation Engine**:
  - **Dynamic Discovery**: Automatically discovers all engine plugins in the `engines/` directory.
  - **Out of the Box**: Built-in free engines based on `translators`.
  - **Easy Expansion**: Supports advanced engines like `OpenAI` and provides clear guidelines for easily adding your own engines.
- **Intelligent Configuration**: Uses `Pydantic` for type-safe configuration management and can automatically load from `.env` files.
- **Robust Workflow**:
  - **Background Processing**: Separation of `request` (registration) and `process` (handling) ensures quick API responses.
  - **Automatic Retry**: Built-in retry mechanism with exponential backoff to gracefully handle network fluctuations.
  - **Rate Limiting**: Configurable token bucket rate limiter to protect your API key.
- **Data Lifecycle Management**: Built-in garbage collection (GC) functionality to regularly clean up outdated data.

## **🚀 Quick Start**

We have provided several 'living document' examples to help you quickly understand the usage of `Trans-Hub`.

1.  **Basic Usage**: Learn how to complete your first translation task in 5 minutes.
    ```bash
    # For details, please check the comments in the file
    poetry run python examples/01_basic_usage.py
    ```

2.  **Real World Simulation**: Want to see how `Trans-Hub` performs in a high concurrency, multi-task environment? This ultimate demonstration will run content producers, background translation workers, and API query services simultaneously.
    ```bash
    # (You need to configure the OpenAI API key in the .env file first)
    poetry run python examples/02_real_world_simulation.py
    ```

For more specific use cases (such as translating `.strings` files), please browse the `examples/` directory directly.

## **📚 Document**

We have a comprehensive documentation library to help you gain a deeper understanding of all aspects of `Trans-Hub`.

👉 [Click here to start exploring our documentation](./docs/en/index.md)

## **Contribution**

We warmly welcome any form of contribution! Please read our **[Contribution Guidelines](./CONTRIBUTING.md)** to get started.

## **License**

This project uses the MIT License. See the [LICENSE.md](./LICENSE.md) file for details.

</details>

<details>
<summary><strong>简体中文</strong></summary>

> **一个为 Python 设计的可嵌入异步本地化引擎，专用于自动化动态内容翻译。**

`Trans-Hub` 是一个**异步优先**、可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。它旨在统一和简化多语言翻译工作流，通过智能缓存、可插拔的翻译引擎、以及健壮的错误处理和策略控制，为上层应用提供高效、低成本、高可靠的翻译能力。

## **核心特性**

- **纯异步设计**: 基于 `asyncio` 构建，与 FastAPI, Starlette 等现代 Python Web 框架完美集成。
- **持久化缓存**: 所有翻译请求和结果都会被自动存储在 SQLite 数据库中，避免重复翻译，节省成本。
- **插件化翻译引擎**:
  - **动态发现**: 自动发现 `engines/` 目录下的所有引擎插件。
  - **开箱即用**: 内置基于 `translators` 的免费引擎。
  - **轻松扩展**: 支持 `OpenAI` 等高级引擎，并提供清晰的指南让你轻松添加自己的引擎。
- **智能配置**: 使用 `Pydantic` 进行类型安全的配置管理，并能从 `.env` 文件自动加载。
- **健壮的工作流**:
  - **后台处理**: `request` (登记) 和 `process` (处理) 分离，确保 API 快速响应。
  - **自动重试**: 内置带指数退避的重试机制，优雅处理网络抖动。
  - **速率限制**: 可配置的令牌桶速率限制器，保护你的 API 密钥。
- **数据生命周期管理**: 内置垃圾回收（GC）功能，定期清理过时数据。

## **🚀 快速上手**

我们提供了多个“活文档”示例，帮助您快速理解 `Trans-Hub` 的用法。

1.  **基础用法**: 学习如何在 5 分钟内完成您的第一个翻译任务。
    ```bash
    # 详情请查看文件内的注释
    poetry run python examples/01_basic_usage.py
    ```

2.  **真实世界模拟**: 想看看 `Trans-Hub` 在高并发、多任务环境下的表现吗？这个终极演示将同时运行内容生产者、后台翻译工作者和 API 查询服务。
    ```bash
    # (需要先在 .env 文件中配置 OpenAI API 密钥)
    poetry run python examples/02_real_world_simulation.py
    ```

更多具体用例（如翻译 `.strings` 文件），请直接浏览 `examples/` 目录。

## **📚 文档**

我们拥有一个全面的文档库，以帮助您深入了解 `Trans-Hub` 的方方面面。

👉 [点击这里开始探索我们的文档](./docs/zh/index.md)

## **贡献**

我们热烈欢迎任何形式的贡献！请阅读我们的 **[贡献指南](./CONTRIBUTING.md)** 来开始。

## **许可证**

本项目采用 MIT 许可证。详见 [LICENSE.md](./LICENSE.md) 文件。

</details>
