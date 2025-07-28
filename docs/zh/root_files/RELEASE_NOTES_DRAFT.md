### **Trans-Hub `v3.0.0` 变更记录 (最终版)**

**版本亮点**

`v3.0.0` 是 Trans-Hub 的一个里程碑式的架构升级版本，其核心是引入了**策略设计模式 (Strategy Pattern)**，将核心翻译处理逻辑从 `Coordinator` 中完全解耦。本次更新极大地提升了系统的可维护性、可扩展性和健壮性。版本新增了**死信队列 (DLQ)** 机制、标准的**引擎生命周期管理**，并建立了完备的**自定义异常体系**和**启动时配置验证**，为未来的功能迭代和生产化部署奠定了坚实的基础。

---

#### **🚀 架构重构 (Refactor)**

*   **核心架构迁移至策略设计模式 (重大变更)**:
    *   引入了 `ProcessingPolicy` 协议和 `DefaultProcessingPolicy` 默认实现，将所有核心业务逻辑（缓存检查、API调用、指数退避重试、DLQ处理）从 `Coordinator` 中剥离并封装。
    *   `Coordinator` 的职责被大幅简化，回归到纯粹的“编排者”角色，负责I/O流转、任务分发和调用策略。
    *   新增 `ProcessingContext` (`@dataclass`)，作为一个轻量级、不可变的“工具箱”在内部高效传递依赖项，替代了之前分散的参数传递。
    *   重构了核心模块的依赖关系，形成严格的单向依赖流，从根本上解决了潜在的循环导入问题。

*   **引擎基类 (`BaseTranslationEngine`) 重构**:
    *   引入 `_atranslate_one` 抽象方法，将通用的并发批处理（`asyncio.gather`）、异常封装和源语言检查逻辑上移至基类 `atranslate_batch` 方法中，极大地简化了具体引擎的实现代码。
    *   新增 `validate_and_parse_context` 方法，为引擎提供了一个统一、标准的上下文验证和解析入口。

*   **配置管理与健壮性重构**:
    *   **引入自定义异常体系**: 新增 `trans_hub/exceptions.py` 模块，定义了 `ConfigurationError`, `EngineNotFoundError` 等语义化异常，替换了原有的通用 `ValueError`，使错误处理更精确、代码更清晰。
    *   **实现启动时配置验证**:
        *   `TransHubConfig` 中的 `active_engine` 字段现在使用 `Enum` 类型，增强了类型安全性和配置的可读性。
        *   为 `TransHubConfig` 添加了 `model_validator`，可在应用启动时立即检查活动引擎的配置是否存在，实现“快速失败”。

#### **✨ 新功能 (Features)**

*   **死信队列 (DLQ) 机制**:
    *   新增了 `th_dead_letter_queue` 数据库表（通过 `002_add_dlq_table.sql` 迁移脚本），用于归档永久失败的翻译任务。
    *   `DefaultProcessingPolicy` 在达到最大重试次数后，会自动将失败任务原子性地移入 DLQ，保持主工作流的清洁。

*   **引擎生命周期管理**:
    *   `BaseTranslationEngine` 新增 `initialize()` 和 `close()` 异步生命周期钩子。
    *   `Coordinator` 现在会在应用启动和关闭时，自动调用所有已发现引擎的这些钩子，为未来需要管理连接池等复杂资源的引擎提供了标准、规范的资源管理接口。

*   **引擎能力声明与智能适配**:
    *   `BaseTranslationEngine` 新增 `ACCEPTS_CONTEXT: bool` 类属性，允许引擎明确声明其处理上下文的能力。
    *   `ProcessingPolicy` 能够智能地读取此标志，仅在引擎支持时才解析和传递上下文，提高了运行效率。

#### **🐛 修复 (Fixes)**

*   **修复了 `openai` 库在代理环境下的网络问题**：通过向 `openai.AsyncOpenAI` 客户端显式注入一个**禁用环境代理** (`trust_env=False`) 的 `httpx.AsyncClient`，从根本上解决了因自动代理检测导致的网络连接失败问题。
*   **修复了 `translators` 库的导入时副作用**：通过将 `import translators` 操作从模块顶层移至 `TranslatorsEngine` 的方法内部（惰性加载），彻底解决了其在特定网络环境下导致应用启动或测试收集阶段崩溃/卡死的问题。
*   修复了多个在 `mypy` 严格模式下发现的类型安全问题，包括 `Enum` 类型赋值、Pydantic 模型实例化以及与无类型提示的第三方库交互。

#### **🔧 其他改进 (Chore & Perf)**

*   **性能优化**: `TranslatorsEngine` 的批处理实现被优化，现在通过一次 `asyncio.to_thread` 调用处理整个批次，显著减少了线程切换开销。
*   **测试覆盖**: 补全了对 `TranslationCache` 和 `RateLimiter` 的单元测试，确保了这些核心工具的逻辑正确性。
*   **健壮性增强**: 为 `schema_manager.py` 中的数据库连接添加了超时，防止进程因数据库锁而无限期阻塞。

---

这份最终版的变更记录准确、全面地反映了我们完成的所有工作。您可以将其存档，或作为 `v3.0.0` 版本的发布说明。