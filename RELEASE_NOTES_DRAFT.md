<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details id='en-details' open ontoggle="if(this.open) document.getElementById('zh-details').open = false;">
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

<details id='zh-details' ontoggle="if(this.open) document.getElementById('en-details').open = false;">
<summary><strong>简体中文</strong></summary>

### **Trans-Hub `v3.0.0` 变更记录**

**版本亮点**

`v3.0.0` 是 Trans-Hub 的一个里程碑式的架构升级版本，其核心是引入了**策略设计模式 (Strategy Pattern)**，将核心翻译处理逻辑从 `Coordinator` 中完全解耦。本次更新极大地提升了系统的可维护性、可扩展性和健robustness。版本新增了**死信队列 (DLQ)** 机制、标准的**引擎生命周期管理**，并建立了完备的**自定义异常体系**和**启动时配置验证**。同时，通过多轮重构解决了所有已知的架构缺陷、运行时 bug 和静态类型问题，为未来的功能迭代和生产化部署奠定了坚如磐石的基础。

#### **🚀 架构重构 (Refactor)**

*   **核心架构迁移至策略设计模式 (重大变更)**:
    *   引入 `ProcessingPolicy` 协议和 `DefaultProcessingPolicy` 默认实现，封装了所有核心业务逻辑（缓存检查、API调用、指数退避重试、DLQ处理）。
    *   `Coordinator` 的职责被大幅简化，回归到纯粹的“编排者”角色，负责I/O流转、任务分发和调用策略。
    *   新增 `ProcessingContext` (`@dataclasses.dataclass`)，作为一个轻量级、不可变的“工具箱”在内部高效传递依赖项。
    *   重构了核心模块的依赖关系，形成严格的单向依赖流，**彻底解决了潜在的循环导入问题**。

*   **引擎基类 (`BaseTranslationEngine`) 重构**:
    *   引入 `_atranslate_one` 抽象方法，将通用的并发批处理（`asyncio.gather`）、异常封装和源语言检查逻辑上移至基类 `atranslate_batch` 方法中，极大地简化了具体引擎的实现代码。
    *   新增 `validate_and_parse_context` 方法，为引擎提供了一个统一、标准的上下文验证和解析入口。

#### **✨ 新功能 (Features)**

*   **死信队列 (DLQ) 机制**:
    *   新增了 `th_dead_letter_queue` 数据库表，用于归档永久失败的翻译任务。
    *   `DefaultProcessingPolicy` 在达到最大重试次数后，会自动将失败任务原子性地移入 DLQ。

*   **引擎生命周期管理**:
    *   `BaseTranslationEngine` 新增 `initialize()` 和 `close()` 异步生命周期钩子。
    *   `Coordinator` 现在会在应用启动和关闭时，自动调用所有已发现引擎的这些钩子，为管理连接池等复杂资源的引擎提供了标准化的接口。

*   **引擎能力声明与智能适配**:
    *   `BaseTranslationEngine` 新增 `ACCEPTS_CONTEXT: bool` 类属性，允许引擎明确声明其处理上下文的能力。
    *   `ProcessingPolicy` 能够智能地读取此标志，仅在引擎支持时才解析和传递上下文。

#### **🐛 修复与健壮性增强 (Fixes & Hardening)**

*   **环境与配置修复**:
    *   **修复了在 CI 环境中因缺少环境变量而导致 `pydantic.ValidationError` 的问题**。通过将所有 `BaseSettings` 模型的配置源统一为仅限环境变量（移除 `env_file`），并为 `OpenAIEngineConfig` 提供健壮的默认值，确保了配置加载在任何环境下都能稳定运行。
    *   修复了 CI 工作流配置 (`ci.yml`)，确保 GitHub Secrets 能被正确地以带 `TH_` 前缀的环境变量形式注入到测试步骤中。

*   **引擎修复**:
    *   **`openai` 引擎**: 通过向 `openai.AsyncOpenAI` 客户端显式注入一个**禁用环境代理** (`trust_env=False`) 的 `httpx.Client`，从根本上解决了因自动代理检测导致的网络连接失败问题。
    *   **`translators` 引擎**: 通过**惰性加载 (Lazy Loading)**，将 `import translators` 操作从模块顶层移至引擎方法内部，彻底解决了其在特定网络环境下因**导入时副作用**（网络 I/O）而导致应用启动或测试收集阶段崩溃/卡死的问题。

*   **类型安全**:
    *   **项目现在 100% 通过 `mypy` 的严格静态类型检查**。修复了所有与 `unittest.mock` 的复杂行为、Pydantic 模型实例化以及 `typing.Generator` 返回类型相关的静态分析错误。

#### **✅ 测试 (Testing)**

*   **建立了全面的自动化测试体系**:
    *   **端到端测试 (`tests/test_main.py`)**: 覆盖了从请求到垃圾回收的完整业务流程，并为所有内置引擎提供了集成测试。
    *   **单元测试 (`tests/unit/`)**:
        *   **[核心修正]** 您的目录中包含 `test_cache.py`, `test_persistence.py`, `test_policies.py`, `test_rate_limiter.py`, `test_utils.py`。这些测试通过深度模拟，精确验证了缓存、持久化、策略、限流和工具函数等核心组件的内部逻辑。
    *   项目的测试覆盖率和健壮性得到大幅提升，为持续集成奠定了基础。

#### **🔧 其他改进 (Chore & Perf)**

*   **性能优化**:
    *   **数据库**: `persistence.py` 中的 `ensure_pending_translations` 方法被重构，现在使用 **UPSERT** 逻辑，显著减少了高并发写入时的数据库 I/O 次数。
    *   **引擎**: `TranslatorsEngine` 的批处理实现被优化，现在通过一次 `asyncio.to_thread` 调用处理整个批次，显著减少了线程切换开销。
*   **开发规范**:
    *   **项目开发宪章**: 创立并完善了 `项目开发宪章`，将本次重构中获得的所有经验教训固化为项目的开发准则和质量标准。
*   **健壮性增强**: 为 `schema_manager.py` 中的数据库连接添加了超时，防止进程因数据库锁而无限期阻塞。

</details>
