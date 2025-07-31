### **Trans-Hub `v3.0.0` 变更记录 (最终修订版)**

**版本亮点**

`v3.0.0` 是 Trans-Hub 的一个里程碑式的架构升级版本。本次更新通过引入**策略设计模式 (Strategy Pattern)**，新增**死信队列 (DLQ)**，并对**数据库持久化层、引擎生命周期管理、配置加载和日志系统**进行了全面的、生产级的重构，极大地提升了系统的可维护性、可扩展性和健壮性。

通过多轮 `刨根问底` 式的调试，我们**彻底解决了**所有已知的架构缺陷（如全局锁、N+1查询、有缺陷的UNIQUE约束）、运行时 bug（如并发冲突、NameError）和静态类型问题，为未来的功能迭代和生产化部署奠定了坚如磐石的基础。

---

#### **🚀 架构重构 (Refactor)**

*   **数据库持久化层 (`persistence`) 彻底重构 (重大变更)**:
    *   **移除全局应用层锁**: 彻底废除了原有的 `asyncio.Lock` 全局锁，解决了严重的性能瓶颈。
    *   **引入原子事务**: 所有涉及多步写入的操作（如 `ensure_pending_translations`, `save_translations`, `garbage_collect`）现在都由数据库层面的**原子事务**保护，从根本上保证了并发安全和数据一致性。
    *   **根除 N+1 查询**: 重构了 `save_translations` 流程，通过在 `TranslationResult` DTO 中传递 `translation_id`，将原有的 N+1 次数据库查询优化为**单次高效的批量 `UPDATE`**。

*   **核心架构迁移至策略设计模式**:
    *   引入 `ProcessingPolicy` 协议和 `DefaultProcessingPolicy` 默认实现，封装了所有核心业务逻辑（缓存检查、API调用、指数退避重试、DLQ处理）。
    *   `Coordinator` 的职责被大幅简化，回归到纯粹的“编排者”角色，负责I/O流转、任务分发和调用策略。
    *   新增 `ProcessingContext`，作为一个轻量级“工具箱”在内部高效传递依赖项。

*   **引擎基类 (`BaseTranslationEngine`) 重构**:
    *   引入 `_atranslate_one` 抽象方法，将通用的并发批处理（`asyncio.gather`）和异常封装逻辑上移至基类，简化了具体引擎的实现。
    *   新增 `validate_and_parse_context` 方法，为引擎提供统一的上下文验证入口。

#### **✨ 新功能 (Features)**

*   **死信队列 (DLQ) 机制**:
    *   新增了 `th_dead_letter_queue` 数据库表。
    *   `DefaultProcessingPolicy` 在达到最大重试次数后，会自动将失败任务原子性地移入 DLQ。

*   **引擎生命周期与惰性加载**:
    *   `BaseTranslationEngine` 新增 `initialize()` 和 `close()` 异步生命周期钩子。
    *   `Coordinator` 的 `__init__` 不再预先实例化所有引擎，而是在**首次请求**该引擎时进行**惰性实例化**，并在 `initialize()` 阶段对**活动引擎**进行健康检查，大幅提升了启动性能和配置灵活性。

*   **优雅美观的日志系统**:
    *   **新增**: 实现了基于 `rich` 和 `structlog` 的**智能混合渲染日志系统**。
    *   对 `WARNING` 及以上级别或包含上下文的关键日志，使用信息丰富的“块状” `Panel` 展示；对常规 `INFO` 日志，则使用紧凑的单行格式，实现了美观与信息密度的完美平衡。

#### **🐛 修复与健壮性增强 (Fixes & Hardening)**

*   **数据库 Schema 健壮性修复 (关键修复)**:
    *   **修复了 `UNIQUE` 约束对 `NULL` 值无效的致命缺陷**。废除了表中原有的 `UNIQUE` 约束，转而使用两个**部分唯一索引 (Partial Unique Indexes)**，从数据库层面彻底保证了业务逻辑（包括 `ON CONFLICT`）在有无上下文两种情况下的唯一性。
    *   修复了 `.sql` 迁移脚本中的注释语法，从 `#` 改为标准的 `--`，解决了 `sqlite3.OperationalError`。

*   **环境与配置修复**:
    *   **修复了 CI 环境中因缺少环境变量而导致的配置失败问题**。通过为 `OpenAIEngineConfig` 提供健壮的默认值，并调整 `Coordinator` 为惰性加载，确保了在任何环境下都能稳定运行。
    *   **新增**: 为 `schema_manager.py` 中的数据库连接添加了超时，防止进程因数据库锁而无限期阻塞。

*   **引擎修复**:
    *   **`openai` 引擎**: 修复了因自动代理检测导致的网络连接失败问题。
    *   **`translators` 引擎**: 通过**惰性加载 (Lazy Loading)**，解决了其在特定网络环境下因**导入时副作用**而导致应用启动崩溃的问题。

*   **Python 包结构修复**:
    *   **新增**: 为 `trans_hub/db/` 等所有包目录添加了 `__init__.py` 文件，解决了 `mypy` 因无法识别命名空间包而产生的、大量误导性的“幽灵错误”。

*   **类型安全**:
    *   **项目现在 100% 通过 `mypy --strict` 静态类型检查**。修复了所有与可选依赖 (`rich`)、泛型 (`MutableMapping`)、mock 对象 (`spec`) 和 `pytest` Fixture 相关的复杂类型注解问题。

#### **✅ 测试 (Testing)**

*   **测试确定性与健壮性**:
    *   **修复了测试中的竞态条件**。废除了所有依赖 `asyncio.sleep` 的脆弱测试，全面采用 `unittest.mock.patch` 来控制时间等不确定性因素，确保所有单元测试都是**确定性的 (deterministic)**。
    *   **修复了 mock 的不精确性**。重构了 `pytest` Fixture，使其能精确地模拟 Pydantic 模型的嵌套结构，消除了因此导致的 `AttributeError`。
*   **建立了全面的自动化测试体系**:
    *   **端到端测试 (`tests/test_main.py`)**: 覆盖了从请求到垃圾回收的完整业务流程。
    *   **单元测试 (`tests/unit/`)**: 包含 `test_cache.py`, `test_persistence.py`, `test_policies.py`, `test_rate_limiter.py`, `test_utils.py`，通过深度模拟精确验证了各核心组件的内部逻辑。

#### **🔧 其他改进 (Chore & Docs)**

*   **项目开发宪章**:
    *   创立并根据本次重构的经验教训，**将宪章从 v2.0 升级至 v3.0**，将所有血泪教训固化为项目的开发准则和质量标准。
*   **代码风格**:
    *   全面修复了 `ruff` 报告的所有代码风格问题，特别是 `E402`（模块导入顺序），使整个代码库符合 PEP 8 的最高标准。