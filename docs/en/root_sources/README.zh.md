
A Python-designed embeddable asynchronous localization engine specifically for automating dynamic content translation.

Trans-Hub is an **asynchronous-first**, embeddable Python application with persistent storage, serving as an intelligent localization (i18n) backend engine. It aims to unify and simplify multilingual translation workflows, providing efficient, low-cost, and highly reliable translation capabilities for upper-layer applications through intelligent caching, pluggable translation engines, and robust error handling and policy control.

---

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

---

## **🚀 Quick Start**

We have provided several examples of 'living documents' to help you quickly understand the usage of `Trans-Hub`.

1. **Basic Usage**: Learn how to complete your first translation task in 5 minutes.  
    ```bash
    # For details, please refer to the comments in the file
    poetry run python examples/01_basic_usage.py
    ```

2.  **Real World Simulation**: Want to see how `Trans-Hub` performs in a high concurrency, multi-task environment? This ultimate demonstration will simultaneously run content producers, backend translators, and API query services.
    ```bash
    # (You need to configure the OpenAI API key in the .env file first)
    poetry run python examples/02_real_world_simulation.py
    ```

For more specific use cases (such as translating `.strings` files), please browse the `examples/` directory directly.

---

## **📚 文档**

我们拥有一个全面的文档库，以帮助您深入了解 `Trans-Hub` 的方方面面。

👉 [点击这里开始探索我们的文档](./docs/en/index.md)

---

## **Contribution**

We warmly welcome any form of contribution! Please read our **[Contribution Guidelines](./CONTRIBUTING.md)** to get started.

## **License**

This project uses the MIT License. See the [LICENSE.md](./LICENSE.md) file for details.