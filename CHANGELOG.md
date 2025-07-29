<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details open>
<summary><strong>English</strong></summary>

**English** | [简体中文](../../zh/root_files/CHANGELOG.md)

# Changelog

All significant changes to this project will be recorded in this document.

The file format follows the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) specification, and the version number follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## **[2.2.0] - 2024-07-26**

This is an important version with functional enhancements and architectural optimizations, introducing a more convenient data query API, and thoroughly restructuring the internal concurrency handling and configuration system, making `Trans-Hub` unprecedentedly robust and easy to expand.

### ✨ Added

- **`Coordinator.get_translation()` method**:
  - `Coordinator` now provides a new public method `get_translation`. This is the **preferred way** to obtain translated content, as it implements an efficient **two-level caching strategy**: it first checks the fast memory cache (L1), and if there is a miss, it queries the persistent storage (L2 / database).

### 🚀 Changes and Optimizations (Changed)

- **[Major Architectural Restructuring] Engine Configuration's "Self-Registration" Mode**:
  - `config.py` has been completely restructured, removing all hardcoded dependencies on specific engines.
  - Introduced `engines/meta.py` as a centralized metadata registry for engine configuration.
  - Now, each engine module will **self-register** its configuration model upon loading, achieving true "convention over configuration" and complete decoupling. This makes the development experience of adding new engines extremely smooth.
- **[Major Architectural Restructuring] Responsibility Shift**:
  - The logic for loading and validating dynamic configurations has been **fully transferred** from the `TransHubConfig` validator to the `__init__` method of `Coordinator`.
  - This change makes `config.py` a pure, static data container, while `Coordinator` acts as an intelligent "assembler," with clearer and more reasonable responsibility division.
- **Concurrency Safety Enhancements**:
  - The internal `DefaultPersistenceHandler` now uses **asynchronous write locks (`asyncio.Lock`)** to protect all database write operations.
  - The implementation of `stream_translatable_items` has been restructured, completely resolving potential **deadlock** issues in high-concurrency scenarios by separating the "locking" and "retrieving" steps.
- **Context Handling Optimization**:
  - The responsibility for context validation has been **delegated** from `Coordinator` to `BaseTranslationEngine`, making engine plugins more self-contained.
  - `Coordinator` now groups batches of tasks retrieved from the database by `context_hash`, ensuring translation accuracy when handling mixed context tasks.

### 🐛 Fixed

- **Fixed the packaging metadata (`extras`) issue**: The way `extras` is defined in `pyproject.toml` has been refactored to ensure that `pip install "trans-hub[...]"` can reliably install all optional dependencies 100% of the time.
- **Fixed all testing (`pytest`) and static analysis (`mypy`) issues**:
  - Resolved various `ValidationError` and `PydanticUserError` caused by Pydantic dynamic models (forward references, `extra="allow"`) in `pytest` fixtures.
  - Completely resolved all `mypy` errors caused by circular dependencies through final architectural refactoring.
  - The test suite now passes consistently and reliably across all supported Python versions.

## **[2.1.0] - 2024-07-26**

This is an important feature and robustness update. It introduces real contextual translation capabilities and has significantly optimized the core configuration system, greatly enhancing the modularity and user-friendliness of the library.

### ✨ Added

- **Dynamic Context Translation**: `OpenAIEngine` now supports passing `system_prompt` through `context`. This allows users to provide detailed system-level instructions for translation requests, enabling precise differentiation of meanings for words like "Jaguar" (the animal) and "Jaguar" (the car brand) based on context, greatly enhancing translation quality.

### 🚀 Changes and Optimizations (Changed)

- **Smart Configuration Loading**: The validator for `TransHubConfig` has been refactored to only attempt to create a default configuration instance when the engine is **explicitly activated** (via the `active_engine` parameter). This makes the engine dependencies of `Trans-Hub` truly modular, allowing users to install only the `extra` engines they need without encountering `ImportError`.

### 🐛 Fixed

- **Fixed the test suite**: Comprehensive fixes and refactoring of `tests/test_main.py`, addressing multiple issues caused by Pydantic validation, `pytest-asyncio` fixtures, and missing dependencies in the CI environment, ensuring the stability and reliability of all tests.

## **[2.0.1] - 2024-07-25**

This is a critical patch version that addresses a configuration loading defect introduced in v2.0.0, greatly enhancing the modularity and user-friendliness of the library.

### 🐛 Fixed

- **Fixed the configuration loading bug**: `TransHubConfig` will now only attempt to create a default configuration instance when the engine is **explicitly activated** (via the `active_engine` parameter).
  - **Impact**: This fix resolves a critical issue where the program would unexpectedly crash when a user only installed an optional engine (e.g., `pip install "trans-hub[openai]"`) and set it as the active engine, due to attempts to initialize other default engines (like `translators`) that were not installed.
  - **Result**: Now, the engine dependencies of `Trans-Hub` are truly modular. Users can install only the `extra` engines they need without encountering `ImportError`.

## **[2.0.0] - 2024-07-25**

This is a **milestone** version that has undergone a comprehensive reconstruction and optimization of the project's core architecture and development experience. `Trans-Hub` is now a more robust, user-friendly, and extensible pure asynchronous localization backend.

### 💥 **Major Changes (BREAKING CHANGES)**

- **Core Architecture: Fully Transitioned to Pure Asynchronous**
  - All core methods of the `Coordinator` class (such as `request`, `process_pending_translations`) are now **purely asynchronous** and must be called using `async/await`. All synchronous methods and code paths have been completely removed.
- **Engine Interface (`BaseTranslationEngine`) Refactoring**
  - The development model of the engine has been **greatly simplified**. Developers now only need to inherit from `BaseTranslationEngine` and implement the `_atranslate_one` asynchronous method. All batch processing and concurrency logic have been moved up to the base class, and `atranslate_batch` no longer needs to be overridden.
- **Persistence Layer (`PersistenceHandler`) Fully Asynchronous**
  - The `PersistenceHandler` interface and its default implementation `DefaultPersistenceHandler` have been refactored to be **purely asynchronous**, with all I/O methods using `async def`.

### ✨ Added

- **Dynamic Context Translation**: `OpenAIEngine` now supports passing `system_prompt` through `context`, achieving true contextual translation that can distinguish between meanings of words like "Jaguar" (the animal) and "Jaguar" (the car).
- **Dynamic Engine Configuration**: `TransHubConfig` can now dynamically and automatically discover and create the required engine configuration instance from `ENGINE_REGISTRY` based on the value of `active_engine`, eliminating the need for manual user configuration and realizing true "convention over configuration."
- **`Coordinator.switch_engine()`**: A convenient synchronous method has been added, allowing for dynamic switching of the currently active translation engine at runtime.
- **Professional Developer and Example Tools**:
  - `tools/inspect_db.py`: A powerful command-line tool has been added for inspecting and interpreting database content.
  - `examples/demo_complex_workflow.py`: An end-to-end demonstration script has been added, showcasing all advanced features such as context, caching, and GC.
- **Comprehensive Documentation Library**: A structured `/docs` directory has been established, providing comprehensive guides, API references, and architectural documentation for users, developers, and contributors.

### 🚀 Changes and Optimizations (Changed)

- **CI/CD and Test Suite**:
  - The GitHub Actions workflow (`ci.yml`) has been completely refactored to use isolated virtual environments, run tests in parallel across multiple Python versions, and integrate Codecov for reporting test coverage.
  - The test suite (`tests/test_main.py`) has been entirely rewritten, implementing **fully isolated and reliable** asynchronous end-to-end tests using `pytest-asyncio` and `fixture`.
- **Dependency Management**:
  - `pyproject.toml` has been refactored, making the core library lighter. Optional translation engines (such as `translators`, `openai`) can now be installed on demand via `extras` (`pip install "trans-hub[openai]"`).
- **Configuration and Logging**:
  - All dependencies that could cause circular imports have been removed, making the configuration system more robust.
  - The `Coordinator` now groups task batches by `context_hash`, ensuring the accuracy of context translations.

### 🐛 Fixed

- **Fixed potential context application errors**: Resolved a logical flaw in the `Coordinator` that could incorrectly apply `context` when handling mixed context batches.
- **Fixed all static type checking errors**: Completely resolved all circular import and type incompatibility issues reported by `mypy` through refactoring and the use of `TYPE_CHECKING`.
- **Fixed all known issues in the CI environment**: Addressed all CI failures, including system package conflicts (`typing-extensions`), `ImportError`, and Pydantic validation errors, ensuring stable operation of the automation process.

## **[1.1.1] - 2025-06-16**

This is a maintenance release focused on improving code quality and developer experience. It completely resolves all static type checking errors in `mypy` strict mode and updates the developer documentation accordingly to ensure that new contributors can follow the most robust best practices.

### 🚀 Changes

- **Developer Documentation Update**:
  - Updated the example code and descriptions in the "Third-Party Engine Development Guide" (`docs/contributing/developing_engines.md`). It now recommends and demonstrates a `mypy`-friendly engine configuration pattern (i.e., field names directly correspond to environment variables instead of using aliases) to ensure that contributors do not encounter static type checking issues when developing new engines.

### 🐛 Fixed

- **Fixed Mypy static type checking errors**:
  - Resolved the `call-arg` (missing argument) error reported by `mypy` when calling configuration classes that inherit from `pydantic-settings.BaseSettings`. The final solution is to use `# type: ignore[call-arg]` at the call site, which maintains the robustness of the backend configuration model (fail-fast principle) while addressing the limitations of static analysis tools.
  - Corrected the improper call to `logging.warning` in the test script (`run_coordinator_test.py`), which used keyword arguments not supported by `mypy`.
- **Normalized the engine configuration model**:
  - The field names of `OpenAIEngineConfig` have been refactored to directly match their corresponding environment variables (minus the `TH_` prefix), for example, `openai_api_key` corresponds to `TH_OPENAI_API_KEY`. This clarifies the intent of the code and is one of the key steps in resolving the `mypy` issues.

## **[1.1.0] - 2025-06-14**

This is an important maintenance and robustness update that primarily addresses data consistency and data flow issues discovered in real-world complex scenarios, making the system more reliable and predictable.

### ✨ Added

- **`__GLOBAL__` sentinel value**: The constant `GLOBAL_CONTEXT_SENTINEL` has been introduced in `trans_hub.types`. This constant is used to represent the case of "no specific context" in the database `context_hash` field, ensuring that the `UNIQUE` constraint works correctly to prevent duplicate records.
- **`PersistenceHandler.get_translation()` method**: A new public interface has been added to directly query successfully translated results from the cache, returning a `TranslationResult` DTO, making it easier for upper-level applications to access cached translations.
- **`PersistenceHandler.get_business_id_for_content()` method**: A new internal method has been added to dynamically query the associated `business_id` based on `content_id` and `context_hash`, serving as a key part of the `business_id` data flow optimization.

### 🚀 Changes

- **Major Changes - Database Schema**:
  - The `context_hash` column in the `th_translations` and `th_sources` tables is now `NOT NULL` and has a default value of `__GLOBAL__`. This completely resolves the issue of duplicate records caused by the special behavior of `NULL` values in SQLite's `UNIQUE` constraint.
  - The `business_id` field has been **removed from the `th_translations` table**. The unique authoritative source for `business_id` is now the `th_sources` table, which makes the data model more normalized and responsibilities clearer.
- **Major Changes - `business_id` Data Flow**:
  - `Coordinator.process_pending_translations()` will **dynamically** call `PersistenceHandler.get_business_id_for_content()` to obtain `business_id` when generating the final `TranslationResult`. This ensures that the `business_id` returned to the user is always consistent with the latest state in the `th_sources` table.
- **GC Logic Optimization**:
  - The `PersistenceHandler.garbage_collect` method now compares based on **date** (`DATE()`) rather than precise timestamps. This makes the behavior when `retention_days=0` (i.e., cleaning up all records before today) more predictable and robust, and simplifies testing.
- **`Coordinator` API Optimization**:
  - The `retention_days` parameter of `Coordinator.run_garbage_collection` has become optional; if not provided, it will fetch the default value from `TransHubConfig`.
  - The `max_retries` and `initial_backoff` parameters of `Coordinator.process_pending_translations` have also become optional, obtaining default values from the `retry_policy` in `TransHubConfig`, enhancing centralized management of configurations.
- **DTO (Data Transfer Object) Evolution**:
  - The `types.ContentItem` DTO has **removed the `business_id` field**, making it more focused on the content to be translated and simplifying internal data flow.
  - The type of the `context_hash` field in `types.TranslationResult` and `types.ContentItem` has changed from `Optional[str]` to `str` to match the database's `NOT NULL` constraint.
- **Core Dependency Changes**:
  - `pydantic-settings` and `python-dotenv` have been elevated from optional dependencies to **core dependencies**. This ensures that all users can utilize the `.env` file to configure any engine, not just `OpenAI`, enhancing the flexibility and robustness of configurations.
- **`PersistenceHandler.stream_translatable_items()` Logic**:
  - Its internal transaction has been split: first, it atomically locks the task in a separate transaction (updating the status to `TRANSLATING`), and then retrieves and `yields` the task details outside of this transaction. This completely resolves the potential issue of transaction nesting when calling `save_translations()` in a loop.

### 🐛 Fixed

- **Fixed the issue of duplicate records in the `th_translations` table**: By introducing the `__GLOBAL__` sentinel value and setting `context_hash` to `NOT NULL`, the fundamental problem of `INSERT OR IGNORE` not preventing duplicate records in the absence of context (`context=None`) has been thoroughly resolved.
- **Fixed the context management protocol error on `sqlite3.Cursor`**: In `PersistenceHandler`, all incompatible `with` statements using `sqlite3.Cursor` have been removed, resolving the `TypeError`.
- **Fixed the spelling error in `Coordinator.request()`**: `self_validate_lang_codes` has been corrected to `self._validate_lang_codes`.
- **Fixed the transaction nesting issue in `PersistenceHandler`**: By refactoring the `stream_translatable_items` method, the transaction for task locking and data retrieval has been separated, preventing `sqlite3.OperationalError: cannot start a transaction within a transaction` when calling `save_translations`.
- **Fixed the issue of missing `business_id` in `TranslationResult`**: By dynamically retrieving `business_id` from `th_sources`, it ensures that `TranslationResult` can correctly reflect its business association, resolving the previous issue where `business_id` always displayed as `None`.
- **Fixed code quality issues**: Resolved multiple unused imports, unnecessary f-strings, and import sorting issues reported by `ruff`, making the code cleaner and more robust.

## **[1.0.0] - 2025-06-12**

This is the first stable version of `Trans-Hub`, marking the full realization and stability of core features.

### ✨ Added

#### **Core Functions and Architecture**

- **Main Coordinator (`Coordinator`)**: Implements the core orchestration logic of the project and serves as the main entry point for interaction with upper-level applications.
- **Persistent Storage**: Built-in SQLite-based persistence layer (`PersistenceHandler`) that supports **transactional write operations** and automatically caches all translation requests and results.
- **Unified Translation Request API (`request`)**: Provides a unified translation request interface that supports two modes: persistent tracking based on `business_id` and ad-hoc translation.
- **Background Processing Workflow (`process_pending_translations`)**: Implements a complete streaming processing flow for retrieving pending tasks, calling the engine, and saving results, supporting retries and rate limiting.

#### **Plugin-based Engine System**

- **Generic Plugin Architecture**: Designed the abstract base class `BaseTranslationEngine` and introduced generics (`typing.Generic`, `typing.TypeVar`), allowing the engine's configuration model (subclass of `BaseEngineConfig`) to be strictly type-bound with the engine class, ensuring type safety and facilitating the extension of new translation engines.
- **Dynamic Engine Discovery**: Implemented a lazy loading mechanism based on `engine_registry`, enabling the system to automatically detect available engines in the environment (based on whether their dependencies are installed), enhancing the system's modularity and user experience.
- **Built-in `TranslatorsEngine`**: Included a free translation engine based on the `translators` library, achieving true "plug and play" functionality without any API Key configuration.
- **Built-in `DebugEngine`**: Provides a debugging translation engine for development and testing, allowing flexible simulation of success and failure scenarios.
- **Built-in `OpenAIEngine`**: Offers a translation engine implementation compatible with OpenAI's API, supporting configuration via a `.env` file, with its configuration model inheriting from both `pydantic_settings.BaseSettings` and `BaseEngineConfig`.

#### **Robustness and Strategy Control**

- **Error Handling and Retry**: The `Coordinator` has a built-in automatic retry mechanism based on the `EngineError` **`is_retryable`** flag, employing an exponential backoff strategy to gracefully handle transient failures (such as `429`, `5xx`, etc.).
- **Parameter Validation**: Strict format validation for parameters such as language codes has been added at the public API entry of the `Coordinator`, achieving "fail fast" and enhancing the robustness of the system.
- **Rate Limiting**: A `RateLimiter` based on the token bucket algorithm has been implemented, which can be injected into the `Coordinator` to precisely control the call rate to external translation APIs, preventing bans due to excessive requests.
- **Garbage Collection (GC) Functionality**: The `run_garbage_collection` method is provided, supporting a `dry_run` mode, allowing for regular cleanup of outdated and orphaned data in the database to ensure the long-term health of the system.

#### **Configuration and Development Experience**

- **Structured Configuration**: Built a type-safe configuration system (`TransHubConfig`) using `Pydantic` and `pydantic-settings`, supporting loading from environment variables and `.env` files.
- **Active `.env` Loading**: Established best practices for actively loading configurations at the program entry point using `dotenv.load_dotenv()`, ensuring robustness in complex environments.
- **Structured Logging**: Integrated `structlog` to implement a structured logging system with `correlation_id`, greatly enhancing observability and correcting type definition issues in `logging_config.py`.
- **Comprehensive Test Suite**: Wrote end-to-end test scripts (`run_coordinator_test.py`) covering all core functionalities.

#### **Document**

- Created the project `README.md`, providing clear quick start guidelines.
- Created `CONTRIBUTING.md` (Contribution Guidelines) and `CODE_OF_CONDUCT.md` (Code of Conduct).
- Created the `.env.example` file to guide users in environment configuration.
- Compiled and improved the "Project Technical Specification Document," "Trans-Hub Cookbook: Practical Examples and Advanced Usage," and "Third-Party Engine Development Guide," providing detailed development and usage instructions.

### 🚀 Changes

- **Architecture Evolution**: The project has evolved from the initial "explicit injection engine instance" to a more advanced and decoupled "dynamic engine discovery and generic binding" architecture, enhancing flexibility and type safety.
- **Default Engine**: Setting `TranslatorsEngine` as the default active engine significantly improved the out-of-the-box experience.
- **Dependency Management**: The `extras` mechanism (`pip install "trans-hub[openai]"`) is used to manage optional engine dependencies, keeping the core library lightweight.
- **Database Schema**: A normalized table structure centered around `th_content` has been finalized, adding a context hash field.
- **Python Version Requirement**: To be compatible with the latest dependency libraries, the minimum Python version requirement for the project has been raised from `3.8` to `3.9`.

### 🐛 Fixed

- Resolved the issue of the `.env` file not being reliably loaded in specific environments (Conda + Poetry + cloud sync drive) by identifying and addressing the problem through two strategies: "modifying environment variable names" and "proactive loading."
- Fixed multiple logical errors discovered during development through test-driven approaches, such as issues with **garbage collection** cascading delete counts, retry logic, and configuration passing.
- Addressed several `ModuleNotFoundError`, `NameError`, and Mypy type checking errors caused by dependencies not being correctly imported or configured, particularly regarding the generic compatibility of `BaseTranslationEngine`, method signatures of the `PersistenceHandler` protocol, and type definitions of `logging_config`.

</details>

<details>
<summary><strong>简体中文</strong></summary>

# 更新日志 (Changelog)

本项目的所有显著变更都将被记录在此文件中。

文件格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) 规范,
版本号遵循 [语义化版本 2.0.0](https://semver.org/spec/v2.0.0.html)。

## **[2.2.0] - 2024-07-26**

这是一个重要的功能增强和架构优化版本，引入了更方便的数据查询 API，并对内部的并发处理和配置系统进行了彻底的重构，使 `Trans-Hub` 变得前所未有的健壮和易于扩展。

### ✨ 新增 (Added)

- **`Coordinator.get_translation()` 方法**:
  - `Coordinator` 现在提供了一个新的 `get_translation` 公共方法。这是获取已翻译内容的**首选方式**，因为它实现了一个高效的**两级缓存策略**：优先查找高速的内存缓存 (L1)，如果未命中，再查询持久化存储 (L2 / 数据库)。

### 🚀 变更与优化 (Changed)

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

### 🐛 修复 (Fixed)

- **修复了打包元数据 (`extras`) 问题**: `pyproject.toml` 中的 `extras` 定义方式被重构，确保了 `pip install "trans-hub[...]" ` 能够 100% 可靠地安装所有可选依赖。
- **修复了所有测试 (`pytest`) 和静态分析 (`mypy`) 问题**:
  - 解决了在 `pytest` 的 fixture 中由 Pydantic 动态模型（前向引用、`extra="allow"`）导致的各种 `ValidationError` 和 `PydanticUserError`。
  - 通过最终的架构重构，彻底解决了所有由循环依赖导致的 `mypy` 错误。
  - 测试套件现在在所有支持的 Python 版本上都能稳定、可靠地通过。

## **[2.1.0] - 2024-07-26**

这是一个重要的功能和健壮性更新版本。它引入了真正的上下文翻译能力，并对核心配置系统进行了重大优化，极大地提升了库的模块化和用户友好性。

### ✨ 新增 (Added)

- **动态上下文翻译**: `OpenAIEngine` 现在支持通过 `context` 传入 `system_prompt`。这允许用户为翻译请求提供详细的系统级指令，从而能够根据上下文精确地区分“Jaguar”（美洲虎）和“Jaguar”（捷豹）等词义，极大地提升了翻译质量。

### 🚀 变更与优化 (Changed)

- **智能配置加载**: `TransHubConfig` 的验证器被重构，现在只会在引擎被**明确激活**时（通过 `active_engine` 参数）才尝试为其创建默认配置实例。这使得 `Trans-Hub` 的引擎依赖是真正模块化的，用户可以只安装他们需要的引擎 `extra` 而不会遇到 `ImportError`。

### 🐛 修复 (Fixed)

- **修复了测试套件**: 全面修复和重构了 `tests/test_main.py`，解决了在 CI 环境中由 Pydantic 验证、`pytest-asyncio` fixture 和依赖项缺失引起的多个问题，确保了所有测试的稳定性和可靠性。

## **[2.0.1] - 2024-07-25**

这是一个关键的修补程序版本，解决了在 v2.0.0 中引入的一个配置加载缺陷，极大地提升了库的模块化和用户友好性。

### 🐛 修复 (Fixed)

- **修复了配置加载的 Bug**: `TransHubConfig` 现在只会在引擎被**明确激活**时（通过 `active_engine` 参数）才尝试为其创建默认配置实例。
  - **影响**: 此修复解决了一个严重问题——当用户只安装了某个可选引擎（例如 `pip install "trans-hub[openai]"`）并将其设为活动引擎时，程序会因为尝试初始化未安装的其他默认引擎（如 `translators`）而意外崩溃。
  - **结果**: 现在，`Trans-Hub` 的引擎依赖是真正模块化的。用户可以只安装他们需要的引擎 `extra`，而不会遇到 `ImportError`。

## **[2.0.0] - 2024-07-25**

这是一个**里程碑式**的版本，对项目的核心架构和开发体验进行了全面的重构和优化。`Trans-Hub` 现在是一个更健壮、更易于使用和扩展的纯异步本地化后端。

### 💥 **重大变更 (BREAKING CHANGES)**

- **架构核心：全面转向纯异步**
  - `Coordinator` 类的所有核心方法（如 `request`, `process_pending_translations`）现在都是**纯异步**的，必须使用 `async/await` 调用。所有同步方法和代码路径已被彻底移除。
- **引擎接口 (`BaseTranslationEngine`) 重构**
  - 引擎的开发模式被**极大地简化**。开发者现在只需继承 `BaseTranslationEngine` 并实现 `_atranslate_one` 异步方法。所有批处理和并发逻辑都已上移到基类中，`atranslate_batch` 不再需要被重写。
- **持久化层 (`PersistenceHandler`) 纯异步化**
  - `PersistenceHandler` 接口及其默认实现 `DefaultPersistenceHandler` 已被重构为**纯异步**，所有 I/O 方法都使用 `async def`。

### ✨ 新增 (Added)

- **动态上下文翻译**: `OpenAIEngine` 现在支持通过 `context` 传入 `system_prompt`，实现了真正的情境翻译，能够根据上下文区分“Jaguar”（美洲虎）和“Jaguar”（捷豹）等词义。
- **动态引擎配置**: `TransHubConfig` 现在可以根据 `active_engine` 的值，**动态地、自动地**从 `ENGINE_REGISTRY` 发现并创建所需的引擎配置实例，无需用户手动配置，实现了真正的“约定优于配置”。
- **`Coordinator.switch_engine()`**: 新增了一个便捷的同步方法，允许在运行时动态地切换当前活动的翻译引擎。
- **专业的开发者与示例工具**:
  - `tools/inspect_db.py`: 新增了一个功能强大的命令行工具，用于检查和解读数据库内容。
  - `examples/demo_complex_workflow.py`: 新增了一个端到端的演示脚本，全面展示了上下文、缓存、GC 等所有高级功能。
- **完整的文档库**: 建立了结构化的 `/docs` 目录，为用户、开发者和贡献者提供了全面的指南、API 参考和架构文档。

### 🚀 变更与优化 (Changed)

- **CI/CD 与测试套件**:
  - GitHub Actions 工作流 (`ci.yml`) 被全面重构，现在使用隔离的虚拟环境，并行测试多个 Python 版本，并集成了 Codecov 以报告测试覆盖率。
  - 测试套件 (`tests/test_main.py`) 被完全重写，使用 `pytest-asyncio` 和 `fixture` 实现了**完全隔离的、可靠的**异步端到端测试。
- **依赖管理**:
  - `pyproject.toml` 被重构，核心库变得更轻量。可选的翻译引擎（如 `translators`, `openai`）现在通过 `extras` (`pip install "trans-hub[openai]"`) 按需安装。
- **配置与日志**:
  - 移除了所有可能导致循环导入的依赖关系，使得配置系统更加健壮。
  - `Coordinator` 现在会按 `context_hash` 对任务批次进行分组处理，确保了上下文翻译的准确性。

### 🐛 修复 (Fixed)

- **修复了潜在的上下文应用错误**: 解决了 `Coordinator` 在处理混合上下文批次时可能错误应用 `context` 的逻辑漏洞。
- **修复了所有静态类型检查错误**: 通过重构和使用 `TYPE_CHECKING`，彻底解决了所有 `mypy` 报告的循环导入和类型不兼容问题。
- **修复了 CI 环境中的所有已知问题**: 解决了包括系统包冲突 (`typing-extensions`)、`ImportError` 和 Pydantic 验证错误在内的所有 CI 故障，确保了自动化流程的稳定运行。

## **[1.1.1] - 2025-06-16**

这是一个以提升代码质量和开发者体验为核心的维护版本。它彻底解决了在 `mypy` 严格模式下的所有静态类型检查错误，并相应地更新了开发者文档，以确保新贡献者能够遵循最健壮的最佳实践。

### 🚀 变更 (Changed)

- **开发者文档更新**:
  - 更新了《第三方引擎开发指南》(`docs/contributing/developing_engines.md`) 中的示例代码和说明。现在它推荐并演示了对 `mypy` 更友好的引擎配置模式（即字段名直接对应环境变量，而非使用别名），以确保贡献者在开发新引擎时不会遇到静态类型检查问题。

### 🐛 修复 (Fixed)

- **修复了 Mypy 静态类型检查错误**:
  - 解决了在调用继承自 `pydantic-settings.BaseSettings` 的配置类时，`mypy` 报告的 `call-arg` (缺少参数) 错误。最终的解决方案是在调用处使用 `# type: ignore[call-arg]`，这既保持了后端配置模型的健壮性（快速失败原则），又解决了静态分析工具的局限性。
  - 修正了测试脚本 (`run_coordinator_test.py`) 中对 `logging.warning` 的不规范调用，该调用使用了 `mypy` 不支持的关键字参数。
- **规范化了引擎配置模型**:
  - `OpenAIEngineConfig` 的字段名被重构，以直接匹配其对应的环境变量（减去 `TH_` 前缀），例如 `openai_api_key` 对应 `TH_OPENAI_API_KEY`。这使得代码意图更清晰，并且是解决 `mypy` 问题的关键步骤之一。

## **[1.1.0] - 2025-06-14**

这是一个重要的维护和健壮性更新版本，主要解决了在实际复杂场景中发现的数据一致性和数据流问题，使系统更加可靠和可预测。

### ✨ 新增 (Added)

- **`__GLOBAL__` 哨兵值**: 在 `trans_hub.types` 中引入了 `GLOBAL_CONTEXT_SENTINEL` 常量。此常量用于在数据库 `context_hash` 字段中表示“无特定上下文”的情况，以确保 `UNIQUE` 约束能够正确工作，防止重复记录。
- **`PersistenceHandler.get_translation()` 方法**: 新增了一个公共接口，用于直接从缓存中查询已成功翻译的结果，返回一个 `TranslationResult` DTO，方便上层应用直接获取已缓存的翻译。
- **`PersistenceHandler.get_business_id_for_content()` 方法**: 新增了一个内部方法，用于根据 `content_id` 和 `context_hash` 动态查询关联的 `business_id`，作为 `business_id` 数据流优化的关键一环。

### 🚀 变更 (Changed)

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

### 🐛 修复 (Fixed)

- **修复了 `th_translations` 表中重复记录问题**: 通过引入 `__GLOBAL__` 哨兵值和将 `context_hash` 设为 `NOT NULL`，彻底解决了在无上下文（`context=None`）的情况下，`INSERT OR IGNORE` 无法阻止重复记录的根本问题。
- **修复了 `sqlite3.Cursor` 上下文管理协议错误**: 在 `PersistenceHandler` 中，所有对 `sqlite3.Cursor` 的使用已移除不兼容的 `with` 语句，解决了 `TypeError`。
- **修复了 `Coordinator.request()` 中的拼写错误**: `self_validate_lang_codes` 已修正为 `self._validate_lang_codes`。
- **修复了 `PersistenceHandler` 中的事务嵌套问题**: 通过重构 `stream_translatable_items` 方法，分离了任务锁定和数据获取的事务，避免了 `save_translations` 调用时发生 `sqlite3.OperationalError: cannot start a transaction within a transaction`。
- **修复了 `TranslationResult` 中 `business_id` 丢失的问题**: 通过从 `th_sources` 动态获取 `business_id`，确保了 `TranslationResult` 能够正确反映其业务关联，解决了之前 `business_id` 总是显示为 `None` 的问题。
- **修复了代码质量问题**: 修复了由 `ruff` 报告的多个未使用的导入、不必要的 f-string 和导入排序问题，使代码更加整洁和健壮。

## **[1.0.0] - 2025-06-12**

这是 `Trans-Hub` 的第一个稳定版本，标志着核心功能的全面实现和稳定。

### ✨ 新增 (Added)

#### **核心功能与架构**

- **主协调器 (`Coordinator`)**: 实现了项目的核心编排逻辑，作为与上层应用交互的主要入口点。
- **持久化存储**: 内置基于 SQLite 的持久化层 (`PersistenceHandler`)，支持**事务性写操作**并自动缓存所有翻译请求和结果。
- **统一翻译请求 API (`request`)**: 提供了统一的翻译请求接口，支持基于 `business_id` 的持久化追踪和即席翻译两种模式。
- **后台处理工作流 (`process_pending_translations`)**: 实现了获取待办任务、调用引擎、保存结果的完整流式处理流程，支持重试和速率限制。

#### **插件化引擎系统**

- **泛型插件化引擎架构**: 设计了 `BaseTranslationEngine` 抽象基类，并引入泛型 (`typing.Generic`, `typing.TypeVar`)，使得引擎的配置模型(`BaseEngineConfig` 的子类)能够与引擎类进行严格的类型绑定，确保类型安全并方便扩展新的翻译引擎。
- **动态引擎发现**: 实现了基于 `engine_registry` 的懒加载机制，系统能自动检测环境中可用的引擎（基于其依赖是否已安装），提升了系统的模块化和用户体验。
- **内置 `TranslatorsEngine`**: 内置了一个基于 `translators` 库的免费翻译引擎，实现了真正的“开箱即用”，无需任何 API Key 配置。
- **内置 `DebugEngine`**: 提供一个用于开发和测试的调试翻译引擎，可灵活模拟成功和失败场景。
- **内置 `OpenAIEngine`**: 提供了对接 OpenAI 兼容 API 的翻译引擎实现，支持通过 `.env` 文件进行配置，其配置模型同时继承 `pydantic_settings.BaseSettings` 和 `BaseEngineConfig`。

#### **健壮性与策略控制**

- **错误处理与重试**: `Coordinator` 内建了基于 `EngineError` 的 **`is_retryable`** 标志的自动重试机制，并采用指数退避策略，优雅地处理临时性故障（如 `429`, `5xx` 等）。
- **参数校验**: 在 `Coordinator` 的公共 API 入口处增加了对语言代码等参数的严格格式校验，实现了“快速失败”，提升了系统的健壮性。
- **速率限制**: 实现了基于令牌桶算法的 `RateLimiter`，可注入 `Coordinator` 以精确控制对外部翻译 API 的调用速率，防止因请求过快而被封禁。
- **垃圾回收 (`GC`) 功能**: 提供了 `run_garbage_collection` 方法，支持 `dry_run` 模式，可定期清理数据库中过时和孤立的数据，保证系统长期健康。

#### **配置与开发体验**

- **结构化配置**: 使用 `Pydantic` 和 `pydantic-settings` 构建了类型安全的配置体系（`TransHubConfig`），支持从环境变量和 `.env` 文件加载。
- **主动 `.env` 加载**: 确立了在程序入口处使用 `dotenv.load_dotenv()` 主动加载配置的最佳实践，以保证在复杂环境下的健壮性。
- **结构化日志**: 集成 `structlog`，实现了带 `correlation_id` 的结构化日志系统，极大地提升了可观测性，并修正了 `logging_config.py` 中的类型定义问题。
- **全面的测试套件**: 编写了覆盖所有核心功能的端到端测试脚本 (`run_coordinator_test.py`)。

#### **文档**

- 创建了项目 `README.md`，提供清晰的快速上手指引。
- 创建了 `CONTRIBUTING.md` (贡献指南) 和 `CODE_OF_CONDUCT.md` (行为准则)。
- 创建了 `.env.example` 文件，指导用户进行环境配置。
- 编写并完善了《项目技术规范文档》、《Trans-Hub Cookbook：实用范例与高级用法》和《第三方引擎开发指南》，提供了详细的开发与使用说明。

### 🚀 变更 (Changed)

- **架构演进**: 项目从最初的“显式注入引擎实例”演进为更高级、更解耦的“动态引擎发现与泛型绑定”架构，提高了灵活性和类型安全性。
- **默认引擎**: 将 `TranslatorsEngine` 设为默认的活动引擎，显著提升了开箱即用体验。
- **依赖管理**: 采用 `extras` 机制 (`pip install "trans-hub[openai]"`) 来管理可选的引擎依赖，保持了核心库的轻量。
- **数据库 Schema**: 最终确定了以 `th_content` 为核心的、规范化的数据表结构，增加了上下文哈希字段。
- **Python 版本要求**: 为了兼容最新的依赖库，项目最低 Python 版本要求从 `3.8` 提升至 `3.9`。

### 🐛 修复 (Fixed)

- 解决了在特定环境（Conda + Poetry + 云同步盘）下，`.env` 文件无法被可靠加载的问题，最终通过“修改环境变量名”和“主动加载”两种策略定位并解决了问题。
- 修复了多个在开发过程中由测试驱动发现的逻辑错误，如**垃圾回收**的级联删除计数问题、重试逻辑与配置传递问题等。
- 解决了多个因依赖项未正确导入或配置导致的 `ModuleNotFoundError`、`NameError` 和 Mypy 类型检查错误，特别是关于 `BaseTranslationEngine` 的泛型兼容性、`PersistenceHandler` 协议的方法签名、以及 `logging_config` 的类型定义。

</details>
