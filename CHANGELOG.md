# 更新日志 (Changelog)

本项目的所有显著变更都将被记录在此文件中。

文件格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) 规范,
版本号遵循 [语义化版本 2.0.0](https://semver.org/spec/v2.0.0.html)。

---

## **[2.1.0] - 2024-07-26**

这是一个重要的功能和健壮性更新版本。它引入了真正的上下文翻译能力，并对核心配置系统进行了重大优化，极大地提升了库的模块化和用户友好性。

### ✨ 新增 (Added)
- **动态上下文翻译**: `OpenAIEngine` 现在支持通过 `context` 传入 `system_prompt`。这允许用户为翻译请求提供详细的系统级指令，从而能够根据上下文精确地区分“Jaguar”（美洲虎）和“Jaguar”（捷豹）等词义，极大地提升了翻译质量。

### 🚀 变更与优化 (Changed)
- **智能配置加载**: `TransHubConfig` 的验证器被重构，现在只会在引擎被**明确激活**时（通过 `active_engine` 参数）才尝试为其创建默认配置实例。这使得 `Trans-Hub` 的引擎依赖是真正模块化的，用户可以只安装他们需要的引擎 `extra` 而不会遇到 `ImportError`。

### 🐛 修复 (Fixed)
- **修复了测试套件**: 全面修复和重构了 `tests/test_main.py`，解决了在 CI 环境中由 Pydantic 验证、`pytest-asyncio` fixture 和依赖项缺失引起的多个问题，确保了所有测试的稳定性和可靠性。

---

## **[2.0.1] - 2024-07-25**

这是一个关键的修补程序版本，解决了在 v2.0.0 中引入的一个配置加载缺陷，极大地提升了库的模块化和用户友好性。

### 🐛 修复 (Fixed)

- **修复了配置加载的 Bug**: `TransHubConfig` 现在只会在引擎被**明确激活**时（通过 `active_engine` 参数）才尝试为其创建默认配置实例。
  - **影响**: 此修复解决了一个严重问题——当用户只安装了某个可选引擎（例如 `pip install "trans-hub[openai]"`）并将其设为活动引擎时，程序会因为尝试初始化未安装的其他默认引擎（如 `translators`）而意外崩溃。
  - **结果**: 现在，`Trans-Hub` 的引擎依赖是真正模块化的。用户可以只安装他们需要的引擎 `extra`，而不会遇到 `ImportError`。

---

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

---

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

---

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
