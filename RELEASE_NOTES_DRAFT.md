<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details open>
<summary><strong>English</strong></summary>

**English** | [简体中文](../../zh/root_files/RELEASE_NOTES_DRAFT.md)

### **Trans-Hub `v3.0.0` Change Log**

Version Highlights

`v3.0.0` is a milestone architectural upgrade version of Trans-Hub, which core introduces the **Strategy Pattern**, completely decoupling the core translation processing logic from the `Coordinator`. This update greatly enhances the system's maintainability, scalability, and robustness. The version adds a **Dead Letter Queue (DLQ)** mechanism, standard **engine lifecycle management**, and establishes a comprehensive **custom exception system** and **configuration validation at startup**. At the same time, it resolves all known architectural defects, runtime bugs, and static type issues through multiple rounds of refactoring, laying a solid foundation for future functional iterations and production deployment.

#### **🚀 Architecture Refactor**

*   **Core architecture migrated to strategy design pattern (major change)**:
    *   Introduced `ProcessingPolicy` protocol and `DefaultProcessingPolicy` default implementation, encapsulating all core business logic (cache checks, API calls, exponential backoff retries, DLQ handling).
    *   The responsibilities of `Coordinator` have been significantly simplified, returning to a purely "orchestrator" role, responsible for I/O flow, task distribution, and calling strategies.
    *   Added `ProcessingContext` (`@dataclasses.dataclass`), serving as a lightweight, immutable "toolbox" for efficiently passing dependencies internally.
    *   Refactored the dependencies of the core module to form a strict unidirectional dependency flow, **completely resolving potential circular import issues**.

*   **Refactoring of the engine base class (`BaseTranslationEngine`)**:
    *   Introduced `_atranslate_one` abstract method, moving common concurrent batch processing (`asyncio.gather`), exception encapsulation, and source language check logic up to the base class `atranslate_batch` method, greatly simplifying the implementation code of specific engines.
    *   Added `validate_and_parse_context` method, providing a unified, standard entry point for context validation and parsing for the engine.

#### **✨ New Features**

*   **Dead Letter Queue (DLQ) Mechanism**:
    *   A new database table `th_dead_letter_queue` has been added to archive permanently failed translation tasks.
    *   `DefaultProcessingPolicy` will automatically and atomically move failed tasks to the DLQ after reaching the maximum retry count.

*   **Engine Lifecycle Management**:
    *   `BaseTranslationEngine` has added asynchronous lifecycle hooks `initialize()` and `close()`.
    *   `Coordinator` will now automatically call these hooks for all discovered engines during application startup and shutdown, providing a standardized interface for managing complex resources like connection pools.

*   **Engine Capability Declaration and Intelligent Adaptation**:
    *   `BaseTranslationEngine` has added a class attribute `ACCEPTS_CONTEXT: bool`, allowing the engine to explicitly declare its ability to handle context.
    *   `ProcessingPolicy` can intelligently read this flag and only parse and pass context when the engine supports it.

#### **🐛 Fixes & Hardening**

*   **Environment and Configuration Fixes**:
    *   **Fixed the issue of `pydantic.ValidationError` caused by missing environment variables in the CI environment**. By unifying the configuration source of all `BaseSettings` models to be environment variable only (removing `env_file`) and providing robust default values for `OpenAIEngineConfig`, it ensures stable configuration loading in any environment.
    *   Fixed the CI workflow configuration (`ci.yml`), ensuring that GitHub Secrets can be correctly injected into the test steps as environment variables prefixed with `TH_`.

*   **Engine Fixes**:
    *   **`openai` engine**: By explicitly injecting an **environment proxy disabled** (`trust_env=False`) `httpx.Client` into the `openai.AsyncOpenAI` client, fundamentally resolved the network connection failure issue caused by automatic proxy detection.
    *   **`translators` engine**: Through **Lazy Loading**, moved the `import translators` operation from the module top level to inside the engine method, completely resolving the application startup or test collection phase crashes/freezes caused by **import side effects** (network I/O) in specific network environments.

*   **Type Safety**:
    *   **The project now passes 100% of `mypy`'s strict static type checks**. Fixed all static analysis errors related to the complex behavior of `unittest.mock`, Pydantic model instantiation, and the return type of `typing.Generator`.

#### **✅ Testing**

*   **Established a comprehensive automated testing system**:
    *   **End-to-end testing (`tests/test_main.py`)**: Covers the complete business process from request to garbage collection and provides integration tests for all built-in engines.
    *   **Unit tests (`tests/unit/`)**:
        *   **[Core Fixes]** Your directory includes `test_cache.py`, `test_persistence.py`, `test_policies.py`, `test_rate_limiter.py`, `test_utils.py`. These tests accurately verify the internal logic of core components such as caching, persistence, policies, rate limiting, and utility functions through deep mocking.
    *   The project's test coverage and robustness have been significantly improved, laying the foundation for continuous integration.

#### **🔧 Other Improvements (Chore & Perf)**

*   **Performance Optimization**:
    *   **Database**: The `ensure_pending_translations` method in `persistence.py` has been refactored to now use **UPSERT** logic, significantly reducing the number of database I/O operations during high-concurrency writes.
    *   **Engine**: The batch processing implementation of `TranslatorsEngine` has been optimized to handle the entire batch with a single `asyncio.to_thread` call, significantly reducing thread switching overhead.
*   **Development Standards**:
    *   **Project Development Charter**: Established and improved the `Project Development Charter`, solidifying all lessons learned from this refactoring into the project's development guidelines and quality standards.
*   **Robustness Enhancement**: Added a timeout for the database connection in `schema_manager.py` to prevent processes from being indefinitely blocked due to database locks.

</details>

<details>
<summary><strong>简体中文</strong></summary>

**English** | [简体中文](../../zh/root_files/RELEASE_NOTES_DRAFT.md)

### **Trans-Hub `v3.0.0` Change Log**

Version Highlights

`v3.0.0` is a milestone architectural upgrade version of Trans-Hub, which core introduces the **Strategy Pattern**, completely decoupling the core translation processing logic from the `Coordinator`. This update greatly enhances the system's maintainability, scalability, and robustness. The version adds a **Dead Letter Queue (DLQ)** mechanism, standard **engine lifecycle management**, and establishes a comprehensive **custom exception system** and **configuration validation at startup**. At the same time, it resolves all known architectural defects, runtime bugs, and static type issues through multiple rounds of refactoring, laying a solid foundation for future functional iterations and production deployment.

#### **🚀 Architecture Refactor**

*   **Core architecture migrated to strategy design pattern (major change)**:
    *   Introduced `ProcessingPolicy` protocol and `DefaultProcessingPolicy` default implementation, encapsulating all core business logic (cache checks, API calls, exponential backoff retries, DLQ handling).
    *   The responsibilities of `Coordinator` have been significantly simplified, returning to a purely "orchestrator" role, responsible for I/O flow, task distribution, and calling strategies.
    *   Added `ProcessingContext` (`@dataclasses.dataclass`), serving as a lightweight, immutable "toolbox" for efficiently passing dependencies internally.
    *   Refactored the dependencies of the core module to form a strict unidirectional dependency flow, **completely resolving potential circular import issues**.

*   **Refactoring of the engine base class (`BaseTranslationEngine`)**:
    *   Introduced `_atranslate_one` abstract method, moving common concurrent batch processing (`asyncio.gather`), exception encapsulation, and source language check logic up to the base class `atranslate_batch` method, greatly simplifying the implementation code of specific engines.
    *   Added `validate_and_parse_context` method, providing a unified, standard entry point for context validation and parsing for the engine.

#### **✨ New Features**

*   **Dead Letter Queue (DLQ) Mechanism**:
    *   A new database table `th_dead_letter_queue` has been added to archive permanently failed translation tasks.
    *   `DefaultProcessingPolicy` will automatically and atomically move failed tasks to the DLQ after reaching the maximum retry count.

*   **Engine Lifecycle Management**:
    *   `BaseTranslationEngine` has added asynchronous lifecycle hooks `initialize()` and `close()`.
    *   `Coordinator` will now automatically call these hooks for all discovered engines during application startup and shutdown, providing a standardized interface for managing complex resources like connection pools.

*   **Engine Capability Declaration and Intelligent Adaptation**:
    *   `BaseTranslationEngine` has added a class attribute `ACCEPTS_CONTEXT: bool`, allowing the engine to explicitly declare its ability to handle context.
    *   `ProcessingPolicy` can intelligently read this flag and only parse and pass context when the engine supports it.

#### **🐛 Fixes & Hardening**

*   **Environment and Configuration Fixes**:
    *   **Fixed the issue of `pydantic.ValidationError` caused by missing environment variables in the CI environment**. By unifying the configuration source of all `BaseSettings` models to be environment variable only (removing `env_file`) and providing robust default values for `OpenAIEngineConfig`, it ensures stable configuration loading in any environment.
    *   Fixed the CI workflow configuration (`ci.yml`), ensuring that GitHub Secrets can be correctly injected into the test steps as environment variables prefixed with `TH_`.

*   **Engine Fixes**:
    *   **`openai` engine**: By explicitly injecting an **environment proxy disabled** (`trust_env=False`) `httpx.Client` into the `openai.AsyncOpenAI` client, fundamentally resolved the network connection failure issue caused by automatic proxy detection.
    *   **`translators` engine**: Through **Lazy Loading**, moved the `import translators` operation from the module top level to inside the engine method, completely resolving the application startup or test collection phase crashes/freezes caused by **import side effects** (network I/O) in specific network environments.

*   **Type Safety**:
    *   **The project now passes 100% of `mypy`'s strict static type checks**. Fixed all static analysis errors related to the complex behavior of `unittest.mock`, Pydantic model instantiation, and the return type of `typing.Generator`.

#### **✅ Testing**

*   **Established a comprehensive automated testing system**:
    *   **End-to-end testing (`tests/test_main.py`)**: Covers the complete business process from request to garbage collection and provides integration tests for all built-in engines.
    *   **Unit tests (`tests/unit/`)**:
        *   **[Core Fixes]** Your directory includes `test_cache.py`, `test_persistence.py`, `test_policies.py`, `test_rate_limiter.py`, `test_utils.py`. These tests accurately verify the internal logic of core components such as caching, persistence, policies, rate limiting, and utility functions through deep mocking.
    *   The project's test coverage and robustness have been significantly improved, laying the foundation for continuous integration.

#### **🔧 Other Improvements (Chore & Perf)**

*   **Performance Optimization**:
    *   **Database**: The `ensure_pending_translations` method in `persistence.py` has been refactored to now use **UPSERT** logic, significantly reducing the number of database I/O operations during high-concurrency writes.
    *   **Engine**: The batch processing implementation of `TranslatorsEngine` has been optimized to handle the entire batch with a single `asyncio.to_thread` call, significantly reducing thread switching overhead.
*   **Development Standards**:
    *   **Project Development Charter**: Established and improved the `Project Development Charter`, solidifying all lessons learned from this refactoring into the project's development guidelines and quality standards.
*   **Robustness Enhancement**: Added a timeout for the database connection in `schema_manager.py` to prevent processes from being indefinitely blocked due to database locks.

</details>
