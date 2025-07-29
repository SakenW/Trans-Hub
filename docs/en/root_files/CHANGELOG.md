**English** | [简体中文](../../zh/root_files/CHANGELOG.md)

---


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
