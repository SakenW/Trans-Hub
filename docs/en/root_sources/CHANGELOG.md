# Changelog

All significant changes to this project will be recorded in this document.

The file format follows the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) specification, and the version number follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

---

## **[2.2.0] - 2024-07-26**

这是一个重要的功能增强和架构优化版本，引入了更方便的数据查询 API，并对内部的并发处理和配置系统进行了彻底的重构，使 `Trans-Hub` 变得前所未有的健壮和易于扩展。

### ✨ Added

- **`Coordinator.get_translation()` 方法**:
  - `Coordinator` 现在提供了一个新的 `get_translation` 公共方法。这是获取已翻译内容的**首选方式**，因为它实现了一个高效的**两级缓存策略**：优先查找高速的内存缓存 (L1)，如果未命中，再查询持久化存储 (L2 / 数据库)。

### 🚀 Changes and Optimizations (Changed)

- **[重大架构重构] 引擎配置的“自我注册”模式**:
  - `config.py` 被彻底重构，移除了所有对具体引擎的硬编码依赖。
  - 引入了 `engines/meta.py` 作为引擎配置的中心化元数据注册表。
  - 现在，每个引擎模块在被加载时都会**自我注册**其配置模型，实现了真正的“约定优于配置”和完全的解耦。这使得添加新引擎的开发体验极其顺滑。
- **[重大架构重构] 职责转移**:
  - 动态配置的加载和验证逻辑，从 `TransHubConfig` 的验证器中**完全移交**给了 `Coordinator` 的 `__init__` 方法。
  - 这个改变使得 `config.py` 变成了一个纯粹、静态的数据容器，而 `Coordinator` 则作为智能的“组装者”，职责划分更加清晰和合理。
- **并发安全增强**:
  - `DefaultPersistenceHandler` 内部现在使用**异步写锁 (`asyncio.Lock`)** 来保护所有数据库写操作。
  - `stream_translatable_items` 的实现被重构，通过分离“锁定”和“获取”步骤，彻底解决了在高并发场景下可能发生的**死锁**问题。
- **上下文处理优化**:
  - 上下文验证的职责从 `Coordinator` **下沉**到了 `BaseTranslationEngine`，使得引擎插件更加自包含。
  - `Coordinator` 现在会按 `context_hash` 对从数据库获取的任务批次进行分组处理，确保了在处理混合上下文任务时的翻译准确性。

### 🐛 Fixed

- **修复了打包元数据 (`extras`) 问题**: `pyproject.toml` 中的 `extras` 定义方式被重构，确保了 `pip install "trans-hub[...]" ` 能够 100% 可靠地安装所有可选依赖。
- **修复了所有测试 (`pytest`) 和静态分析 (`mypy`) 问题**:
  - 解决了在 `pytest` 的 fixture 中由 Pydantic 动态模型（前向引用、`extra="allow"`）导致的各种 `ValidationError` 和 `PydanticUserError`。
  - 通过最终的架构重构，彻底解决了所有由循环依赖导致的 `mypy` 错误。
  - 测试套件现在在所有支持的 Python 版本上都能稳定、可靠地通过。

---

## **[2.1.0] - 2024-07-26**

This is an important feature and robustness update. It introduces real contextual translation capabilities and has made significant optimizations to the core configuration system, greatly enhancing the modularity and user-friendliness of the library.

### ✨ Added

- **Dynamic Context Translation**: `OpenAIEngine` now supports passing `system_prompt` through `context`. This allows users to provide detailed system-level instructions for translation requests, enabling precise differentiation of meanings for words like "Jaguar" (the animal) and "Jaguar" (the car brand) based on context, greatly enhancing translation quality.

### 🚀 Changes and Optimizations (Changed)

- **Smart Configuration Loading**: The validator for `TransHubConfig` has been refactored to only attempt to create a default configuration instance when the engine is **explicitly activated** (via the `active_engine` parameter). This makes the engine dependencies of `Trans-Hub` truly modular, allowing users to install only the `extra` engines they need without encountering `ImportError`.

### 🐛 Fixed

- **Fixed the test suite**: Comprehensive fixes and refactoring of `tests/test_main.py`, addressing multiple issues caused by Pydantic validation, `pytest-asyncio` fixtures, and missing dependencies in the CI environment, ensuring the stability and reliability of all tests.

---

## **[2.0.1] - 2024-07-25**

这是一个关键的修补程序版本，解决了在 v2.0.0 中引入的一个配置加载缺陷，极大地提升了库的模块化和用户友好性。

### 🐛 Fixed

- **修复了配置加载的 Bug**: `TransHubConfig` 现在只会在引擎被**明确激活**时（通过 `active_engine` 参数）才尝试为其创建默认配置实例。
  - **影响**: 此修复解决了一个严重问题——当用户只安装了某个可选引擎（例如 `pip install "trans-hub[openai]"`）并将其设为活动引擎时，程序会因为尝试初始化未安装的其他默认引擎（如 `translators`）而意外崩溃。
  - **结果**: 现在，`Trans-Hub` 的引擎依赖是真正模块化的。用户可以只安装他们需要的引擎 `extra`，而不会遇到 `ImportError`。

---

## **[2.0.0] - 2024-07-25**

This is a **milestone** version that has undergone a comprehensive reconstruction and optimization of the project's core architecture and development experience. `Trans-Hub` is now a more robust, user-friendly, and extensible pure asynchronous localization backend.

### 💥 **Major Changes (BREAKING CHANGES)**

- **Core Architecture: Full Transition to Pure Asynchronous**
  - All core methods of the `Coordinator` class (such as `request`, `process_pending_translations`) are now **purely asynchronous** and must be called using `async/await`. All synchronous methods and code paths have been completely removed.
- **Engine Interface (`BaseTranslationEngine`) Refactoring**
  - The development model of the engine has been **greatly simplified**. Developers now only need to inherit from `BaseTranslationEngine` and implement the `_atranslate_one` asynchronous method. All batch processing and concurrency logic have been moved up to the base class, and `atranslate_batch` no longer needs to be overridden.
- **Persistence Layer (`PersistenceHandler`) Purely Asynchronous**
  - The `PersistenceHandler` interface and its default implementation `DefaultPersistenceHandler` have been refactored to be **purely asynchronous**, with all I/O methods using `async def`.

### ✨ Added

- **Dynamic Context Translation**: `OpenAIEngine` now supports passing `system_prompt` through `context`, achieving true contextual translation that can distinguish between meanings of words like "Jaguar" (the animal) and "Jaguar" (the car).
- **Dynamic Engine Configuration**: `TransHubConfig` can now dynamically and automatically discover and create the required engine configuration instances from `ENGINE_REGISTRY` based on the value of `active_engine`, eliminating the need for manual user configuration and realizing true "convention over configuration."
- **`Coordinator.switch_engine()`**: A convenient synchronous method has been added, allowing for dynamic switching of the currently active translation engine at runtime.
- **Professional Developer and Example Tools**:
  - `tools/inspect_db.py`: A powerful command-line tool has been added for inspecting and interpreting database content.
  - `examples/demo_complex_workflow.py`: An end-to-end demonstration script has been added, showcasing all advanced features such as context, caching, and GC.
- **Comprehensive Documentation Library**: A structured `/docs` directory has been established, providing users, developers, and contributors with comprehensive guides, API references, and architectural documentation.

### 🚀 Changes and Optimizations (Changed)

- **CI/CD and Test Suite**:
  - The GitHub Actions workflow (`ci.yml`) has been completely refactored to use isolated virtual environments, run tests in parallel across multiple Python versions, and integrate Codecov for reporting test coverage.
  - The test suite (`tests/test_main.py`) has been completely rewritten, implementing **fully isolated and reliable** asynchronous end-to-end tests using `pytest-asyncio` and `fixture`.
- **Dependency Management**:
  - `pyproject.toml` has been refactored, making the core library lighter. Optional translation engines (such as `translators`, `openai`) can now be installed on demand via `extras` (`pip install "trans-hub[openai]"`).
- **Configuration and Logging**:
  - All dependencies that could cause circular imports have been removed, making the configuration system more robust.
  - The `Coordinator` now groups task batches by `context_hash`, ensuring the accuracy of context translations.

### 🐛 Fixed

- **Fixed potential context application errors**: Resolved a logical flaw in the `Coordinator` that could incorrectly apply `context` when handling mixed context batches.
- **Fixed all static type checking errors**: Thoroughly addressed all circular import and type incompatibility issues reported by `mypy` through refactoring and the use of `TYPE_CHECKING`.
- **Fixed all known issues in the CI environment**: Resolved all CI failures, including system package conflicts (`typing-extensions`), `ImportError`, and Pydantic validation errors, ensuring stable operation of the automation process.

---

## **[1.1.1] - 2025-06-16**

这是一个以提升代码质量和开发者体验为核心的维护版本。它彻底解决了在 `mypy` 严格模式下的所有静态类型检查错误，并相应地更新了开发者文档，以确保新贡献者能够遵循最健壮的最佳实践。

### 🚀 Changes

- **开发者文档更新**:
  - 更新了《第三方引擎开发指南》(`docs/contributing/developing_engines.md`) 中的示例代码和说明。现在它推荐并演示了对 `mypy` 更友好的引擎配置模式（即字段名直接对应环境变量，而非使用别名），以确保贡献者在开发新引擎时不会遇到静态类型检查问题。

### 🐛 Fixed

- **修复了 Mypy 静态类型检查错误**:
  - 解决了在调用继承自 `pydantic-settings.BaseSettings` 的配置类时，`mypy` 报告的 `call-arg` (缺少参数) 错误。最终的解决方案是在调用处使用 `# type: ignore[call-arg]`，这既保持了后端配置模型的健壮性（快速失败原则），又解决了静态分析工具的局限性。
  - 修正了测试脚本 (`run_coordinator_test.py`) 中对 `logging.warning` 的不规范调用，该调用使用了 `mypy` 不支持的关键字参数。
- **规范化了引擎配置模型**:
  - `OpenAIEngineConfig` 的字段名被重构，以直接匹配其对应的环境变量（减去 `TH_` 前缀），例如 `openai_api_key` 对应 `TH_OPENAI_API_KEY`。这使得代码意图更清晰，并且是解决 `mypy` 问题的关键步骤之一。

## **[1.1.0] - 2025-06-14**

这是一个重要的维护和健壮性更新版本，主要解决了在实际复杂场景中发现的数据一致性和数据流问题，使系统更加可靠和可预测。

### ✨ Added

- **`__GLOBAL__` 哨兵值**: 在 `trans_hub.types` 中引入了 `GLOBAL_CONTEXT_SENTINEL` 常量。此常量用于在数据库 `context_hash` 字段中表示“无特定上下文”的情况，以确保 `UNIQUE` 约束能够正确工作，防止重复记录。
- **`PersistenceHandler.get_translation()` 方法**: 新增了一个公共接口，用于直接从缓存中查询已成功翻译的结果，返回一个 `TranslationResult` DTO，方便上层应用直接获取已缓存的翻译。
- **`PersistenceHandler.get_business_id_for_content()` 方法**: 新增了一个内部方法，用于根据 `content_id` 和 `context_hash` 动态查询关联的 `business_id`，作为 `business_id` 数据流优化的关键一环。

### 🚀 Changes

- **重大变更 - 数据库 Schema**:
  - `th_translations` 表和 `th_sources` 表中的 `context_hash` 列现在是 `NOT NULL`，并有默认值 `__GLOBAL__`。这彻底解决了 SQLite `UNIQUE` 约束中 `NULL` 值的特殊行为导致的重复记录问题。
  - `th_translations` 表**已移除 `business_id` 字段**。`business_id` 的唯一权威来源现在是 `th_sources` 表，这使得数据模型更加规范化，职责更清晰。
- **重大变更 - `business_id` 数据流**:
  - `Coordinator.process_pending_translations()` 在生成最终的 `TranslationResult` 时，会**动态地**调用 `PersistenceHandler.get_business_id_for_content()` 来获取 `business_id`。这确保了返回给用户的 `business_id` 始终与 `th_sources` 表中的最新状态保持一致。
- **GC 逻辑优化**:
  - `PersistenceHandler.garbage_collect` 方法现在基于**日期** (`DATE()`) 而非精确时间戳进行比较。这使得 `retention_days=0` 时的行为（即清理所有今天之前的记录）更加可预测和健壮，并简化了测试。
- **`Coordinator` API 优化**:
  - `Coordinator.run_garbage_collection` 的 `retention_days` 参数变为可选，如果未提供，则会从 `TransHubConfig` 中获取默认值。
  - `Coordinator.process_pending_translations` 的 `max_retries` 和 `initial_backoff` 参数也变为可选，会从 `TransHubConfig` 中的 `retry_policy` 获取默认值，增强了配置的集中管理。
- **DTO (数据传输对象) 演进**:
  - `types.ContentItem` DTO **移除了 `business_id` 字段**，使其更专注于待翻译的内容本身，简化了内部数据流。
  - `types.TranslationResult` 和 `types.ContentItem` 中的 `context_hash` 字段类型从 `Optional[str]` 变更为 `str`，以匹配数据库的 `NOT NULL` 约束。
- **核心依赖变更**:
  - `pydantic-settings` 和 `python-dotenv` 已从可选依赖提升为**核心依赖**。这确保了所有用户都能利用 `.env` 文件来配置任何引擎，而不仅仅是 `OpenAI`，增强了配置的灵活性和健壮性。
- **`PersistenceHandler.stream_translatable_items()` 逻辑**:
  - 其内部事务已拆分：先在一个独立的事务中原子性地锁定任务（更新状态为 `TRANSLATING`），然后在此事务外部获取并 `yield` 任务详情。这彻底解决了在循环中调用 `save_translations()` 时可能发生的事务嵌套问题。

### 🐛 Fixed

- **修复了 `th_translations` 表中重复记录问题**: 通过引入 `__GLOBAL__` 哨兵值和将 `context_hash` 设为 `NOT NULL`，彻底解决了在无上下文（`context=None`）的情况下，`INSERT OR IGNORE` 无法阻止重复记录的根本问题。
- **修复了 `sqlite3.Cursor` 上下文管理协议错误**: 在 `PersistenceHandler` 中，所有对 `sqlite3.Cursor` 的使用已移除不兼容的 `with` 语句，解决了 `TypeError`。
- **修复了 `Coordinator.request()` 中的拼写错误**: `self_validate_lang_codes` 已修正为 `self._validate_lang_codes`。
- **修复了 `PersistenceHandler` 中的事务嵌套问题**: 通过重构 `stream_translatable_items` 方法，分离了任务锁定和数据获取的事务，避免了 `save_translations` 调用时发生 `sqlite3.OperationalError: cannot start a transaction within a transaction`。
- **修复了 `TranslationResult` 中 `business_id` 丢失的问题**: 通过从 `th_sources` 动态获取 `business_id`，确保了 `TranslationResult` 能够正确反映其业务关联，解决了之前 `business_id` 总是显示为 `None` 的问题。
- **修复了代码质量问题**: 修复了由 `ruff` 报告的多个未使用的导入、不必要的 f-string 和导入排序问题，使代码更加整洁和健壮。

---

## **[1.0.0] - 2025-06-12**

This is the first stable version of `Trans-Hub`, marking the full realization and stability of core features.

### ✨ Added

#### **Core Functions and Architecture**

- **Main Coordinator (`Coordinator`)**: Implements the core orchestration logic of the project and serves as the main entry point for interaction with upper-level applications.
- **Persistent Storage**: Built-in SQLite-based persistence layer (`PersistenceHandler`) that supports **transactional write operations** and automatically caches all translation requests and results.
- **Unified Translation Request API (`request`)**: Provides a unified translation request interface that supports two modes: persistent tracking based on `business_id` and ad-hoc translation.
- **Background Processing Workflow (`process_pending_translations`)**: Implements a complete streaming processing flow for retrieving pending tasks, invoking the engine, and saving results, supporting retries and rate limiting.

#### **Plugin-based Engine System**

- **Generic Plugin Architecture**: Designed the abstract base class `BaseTranslationEngine` and introduced generics (`typing.Generic`, `typing.TypeVar`), allowing the engine's configuration model (subclass of `BaseEngineConfig`) to be strictly type-bound with the engine class, ensuring type safety and facilitating the extension of new translation engines.
- **Dynamic Engine Discovery**: Implemented a lazy loading mechanism based on `engine_registry`, enabling the system to automatically detect available engines in the environment (based on whether their dependencies are installed), enhancing the system's modularity and user experience.
- **Built-in `TranslatorsEngine`**: Included a free translation engine based on the `translators` library, achieving true "plug-and-play" functionality without any API Key configuration.
- **Built-in `DebugEngine`**: Provides a debugging translation engine for development and testing, allowing flexible simulation of success and failure scenarios.
- **Built-in `OpenAIEngine`**: Offers a translation engine implementation compatible with OpenAI's API, supporting configuration via a `.env` file, with its configuration model inheriting from both `pydantic_settings.BaseSettings` and `BaseEngineConfig`.

#### **Robustness and Strategy Control**

- **Error Handling and Retry**: The `Coordinator` has a built-in automatic retry mechanism based on the `EngineError` **`is_retryable`** flag, employing an exponential backoff strategy to gracefully handle transient failures (such as `429`, `5xx`, etc.).
- **Parameter Validation**: Strict format validation for parameters such as language codes has been added at the public API entry of the `Coordinator`, achieving "fast failure" and enhancing the robustness of the system.
- **Rate Limiting**: A `RateLimiter` based on the token bucket algorithm has been implemented, which can be injected into the `Coordinator` to precisely control the call rate to external translation APIs, preventing bans due to excessive requests.
- **Garbage Collection (`GC`) Functionality**: The `run_garbage_collection` method is provided, supporting a `dry_run` mode, allowing for regular cleanup of outdated and orphaned data in the database to ensure the long-term health of the system.

#### **Configuration and Development Experience**

- **Structured Configuration**: Built a type-safe configuration system (`TransHubConfig`) using `Pydantic` and `pydantic-settings`, supporting loading from environment variables and `.env` files.
- **Active `.env` Loading**: Established best practices for actively loading configurations using `dotenv.load_dotenv()` at the program entry point to ensure robustness in complex environments.
- **Structured Logging**: Integrated `structlog` to implement a structured logging system with `correlation_id`, greatly enhancing observability and fixing type definition issues in `logging_config.py`.
- **Comprehensive Test Suite**: Wrote end-to-end test scripts (`run_coordinator_test.py`) covering all core functionalities.

#### **Document**

- Created the project `README.md`, providing clear quick start guidelines.
- Created `CONTRIBUTING.md` (Contribution Guidelines) and `CODE_OF_CONDUCT.md` (Code of Conduct).
- Created the `.env.example` file to guide users in environment configuration.
- Compiled and improved the "Project Technical Specification Document," "Trans-Hub Cookbook: Practical Examples and Advanced Usage," and "Third-Party Engine Development Guide," providing detailed development and usage instructions.

### 🚀 Changes

- **Architecture Evolution**: The project has evolved from the initial "explicit injection of engine instances" to a more advanced and decoupled "dynamic engine discovery and generic binding" architecture, enhancing flexibility and type safety.
- **Default Engine**: Setting `TranslatorsEngine` as the default active engine significantly improves the out-of-the-box experience.
- **Dependency Management**: The `extras` mechanism (`pip install "trans-hub[openai]"`) is used to manage optional engine dependencies, keeping the core library lightweight.
- **Database Schema**: A normalized table structure centered around `th_content` has been finalized, adding a context hash field.
- **Python Version Requirement**: To be compatible with the latest dependency libraries, the minimum Python version requirement for the project has been raised from `3.8` to `3.9`.

### 🐛 Fixed

- Resolved the issue of the `.env` file not being reliably loaded in specific environments (Conda + Poetry + cloud sync drive) by identifying and addressing the problem through two strategies: "modifying environment variable names" and "proactive loading."
- Fixed multiple logical errors discovered during development through test-driven approaches, such as issues with **garbage collection** cascading delete counts, retry logic, and configuration passing.
- Addressed several `ModuleNotFoundError`, `NameError`, and Mypy type checking errors caused by dependencies not being correctly imported or configured, particularly regarding the generic compatibility of `BaseTranslationEngine`, method signatures of the `PersistenceHandler` protocol, and the type definition of `logging_config`.
