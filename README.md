# Trans-Hub：您的异步本地化后端引擎 🚀

[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![Python versions](https://img.shields.io/pypi/pyversions/trans-hub.svg)](https://pypi.org/project/trans-hub)
[![CI/CD Status](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`Trans-Hub` 是一个强大、异步优先、可嵌入 Python 应用程序的本地化（i18n）后端引擎。**

它旨在统一和简化多语言翻译工作流。通过**智能缓存、插件化翻译引擎、自动重试和速率限制**，`Trans-Hub` 为您的应用提供高效、低成本、高可靠的翻译能力。

最棒的是，`Trans-Hub` **开箱即用**！它内置了强大的免费翻译引擎，让您无需任何 API Key 或复杂配置，即可在几分钟内开始翻译。

---

## ✨ 核心特性

- **异步优先**: 从底层完全异步设计，为高并发环境而生，可与 FastAPI、aiohttp 等现代异步框架无缝集成。
- **零配置启动**: 内置免费翻译引擎，实现真正的“开箱即用”。
- **持久化缓存**: 自动将翻译结果存储在本地数据库中，极大降低 API 成本。
- **🔌 真正的插件化架构**: 按需安装，轻松扩展自定义引擎。
- **健壮的错误处理**: 内置自动重试和指数退避策略。
- **⚙️ 精准的策略控制**: 内置速率限制器，并支持上下文（Context）感知翻译。
- **生命周期管理**: 内置垃圾回收（GC）功能，定期清理过时数据。
- **专业级可观测性**: 支持结构化的 JSON 日志。

## 🚀 快速上手

在5分钟内完成您的第一次翻译，无需任何 API Key！

1.  **安装**:
    ```bash
    pip install trans-hub
    ```
2.  **创建脚本**: 创建一个 `quick_start.py` 文件并复制代码。
3.  **运行**:
    ```bash
    python quick_start.py
    ```

➡️ **欲获取完整的代码和分步详解，请访问我们的 [【快速入门指南】](./docs/guides/01_quickstart.md)**

---

## 升级到高级引擎 (例如 OpenAI)

当您需要更高质量的翻译时，升级过程非常简单：

1.  **安装可选依赖**: `pip install "trans-hub[openai]"`
2.  **配置 `.env` 文件**: 添加您的 `TH_OPENAI_API_KEY` 等信息。
3.  **激活引擎**: 在代码中，只需一行即可切换：
    ```python
    config = TransHubConfig(active_engine="openai")
    ```

## 核心概念

- **Coordinator**: 负责编排整个**异步**翻译工作流的核心对象。
- **Engine**: 翻译服务的具体实现，可被动态发现和切换。
- **`request()`**: 轻量级地“登记”一个翻译需求。
- **`process_pending_translations()`**: “执行”实际的翻译工作，建议在后台运行。

## 深入了解

我们为您准备了详尽的文档库，覆盖了从快速入门到架构设计的方方面面。

### ➡️ [**探索官方文档中心**](./docs/INDEX.md)

- **使用指南**: 学习高级功能。
- **API 参考**: 查阅精确的接口定义。
- **架构文档**: 了解内部工作原理。
- **贡献指南**: 学习如何贡献新引擎。

## 贡献

我们热烈欢迎任何形式的贡献！请先阅读我们的 **[贡献指南](./CONTRIBUTING.md)**。

## 行为准则

请遵守我们的 **[行为准则](./CODE_OF_CONDUCT.md)**。

## 许可证

`Trans-Hub` 采用 [MIT 许可证](./LICENSE.md)。