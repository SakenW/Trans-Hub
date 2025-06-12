# 更新日志 (Changelog)

本项目的所有显著变更都将被记录在此文件中。

文件格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) 规范,
版本号遵循 [语义化版本 2.0.0](https://semver.org/spec/v2.0.0.html)。

---

## [1.0.0] - 2024-06-12

这是 `Trans-Hub` 的第一个稳定版本，标志着核心功能的全面实现和稳定。

### ✨ 新增 (Added)

#### **核心功能**
*   **主协调器 (`Coordinator`)**: 实现了项目的核心编排逻辑，作为与上层应用交互的主要入口点。
*   **持久化存储**: 内置基于 SQLite 的持久化层 (`PersistenceHandler`)，自动缓存所有翻译请求和结果。
*   **统一翻译请求 API (`request`)**: 提供了统一的翻译请求接口，支持基于 `business_id` 的持久化追踪和即席翻译两种模式。
*   **后台处理工作流 (`process_pending_translations`)**: 实现了获取待办任务、调用引擎、保存结果的完整流式处理流程。

#### **引擎系统**
*   **插件化引擎架构**: 设计了 `BaseTranslationEngine` 抽象基类，使系统可以轻松扩展新的翻译引擎。
*   **动态引擎发现**: 实现了基于 `engine_registry` 的懒加载机制，系统能自动检测环境中可用的引擎（基于其依赖是否已安装），提升了系统的模块化和用户体验。
*   **内置 `TranslatorsEngine`**: 内置了一个基于 `translators` 库的免费翻译引擎，实现了真正的“开箱即用”，无需任何 API Key 配置。
*   **内置 `DebugEngine`**: 提供一个用于开发和测试的伪翻译引擎，可灵活模拟成功和失败场景。
*   **内置 `OpenAIEngine`**: 提供了对接 OpenAI 兼容 API 的翻译引擎实现，支持通过 `.env` 文件进行配置。

#### **健壮性与策略**
*   **错误处理与重试**: `Coordinator` 内建了基于 `is_retryable` 标志的自动重试机制，并采用指数退避策略，优雅地处理临时性故障。
*   **参数校验**: 在 `Coordinator` 的公共 API 入口处增加了对语言代码等参数的格式校验，实现了“快速失败”。
*   **速率限制**: 实现了基于令牌桶算法的 `RateLimiter`，可注入 `Coordinator` 以精确控制对外部 API 的调用速率。
*   **垃圾回收 (GC)**: 提供了 `run_garbage_collection` 功能，可定期清理数据库中过时和孤立的数据，保证系统长期健康。

#### **配置与开发体验**
*   **结构化配置**: 使用 `Pydantic` 和 `pydantic-settings` 构建了类型安全的配置体系（`TransHubConfig`）。
*   **主动 `.env` 加载**: 确立了在程序入口处使用 `dotenv.load_dotenv()` 主动加载配置的最佳实践，以保证在复杂环境下的健壮性。
*   **结构化日志**: 集成 `structlog`，实现了带 `correlation_id` 的结构化日志系统，极大地提升了可观测性。
*   **全面的测试套件**: 编写了覆盖所有核心功能的端到端测试脚本 (`run_coordinator_test.py`)。

#### **文档**
*   创建了项目 `README.md`，提供清晰的快速上手指引。
*   创建了 `CONTRIBUTING.md` (贡献指南) 和 `CODE_OF_CONDUCT.md` (行为准则)。
*   创建了 `.env.example` 文件，指导用户进行环境配置。
*   编写了《技术规范文档》、《Cookbook》和《第三方引擎开发指南》。

### 🚀 变更 (Changed)

*   **架构演进**: 项目从最初的“显式注入引擎实例”演进为更高级、更解耦的“动态引擎发现”架构。
*   **默认引擎**: 将 `TranslatorsEngine` 设为默认的活动引擎，提升了开箱即用体验。
*   **依赖管理**: 采用 `extras` 机制 (`pip install "trans-hub[openai]"`) 来管理可选的引擎依赖，保持了核心库的轻量。
*   **数据库 Schema**: 最终确定了以 `th_content` 为核心的、规范化的数据表结构。
*   **Python 版本**: 为了兼容最新的依赖库，项目最低 Python 版本要求从 `3.8` 提升至 `3.9`。

### 🐛 修复 (Fixed)

*   解决了在特定环境（Conda + Poetry + 云同步盘）下，`.env` 文件无法被可靠加载的问题，最终通过“修改环境变量名”和“主动加载”两种策略定位并解决了问题。
*   修复了多个在开发过程中由测试驱动发现的逻辑错误，如 GC 的级联删除计数问题、重试逻辑与配置传递问题等。
*   解决了多个因依赖项未正确安装或配置导致的 `ModuleNotFoundError` 和 `NameError`。
````