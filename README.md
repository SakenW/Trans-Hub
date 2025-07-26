# Trans-Hub：您的异步本地化后端引擎 🚀

[![Python CI/CD Pipeline](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/SakenW/trans-hub/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/SakenW/trans-hub)
[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

`Trans-Hub` 是一个**异步优先**、可嵌入 Python 应用程序的、带持久化存储的智能本地化（i18n）后端引擎。它旨在统一和简化多语言翻译工作流，通过智能缓存、可插拔的翻译引擎、以及健壮的错误处理和策略控制，为上层应用提供高效、低成本、高可靠的翻译能力。

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

---

## **📚 文档**

我们拥有一个全面的文档库，以帮助您深入了解 `Trans-Hub` 的方方面面。

👉 **[点击这里开始探索我们的文档](./docs/INDEX.md)**

---

## **贡献**

我们热烈欢迎任何形式的贡献！请阅读我们的 **[贡献指南](./CONTRIBUTING.md)** 来开始。

## **许可证**

本项目采用 MIT 许可证。详见 [LICENSE.md](./LICENSE.md) 文件。