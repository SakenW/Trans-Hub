<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->
<details open>
<summary><strong>English</strong></summary>

### **Trans-Hub Unified Development Roadmap (v2.2 Final Version)**

**Current Status**: The **first phase of the core library: Performance and Core Optimization** has been fully completed (the `v3.0.0` milestone has been achieved). The codebase quality is stable, the architecture is clear, performance has been optimized, and it has passed 100% of all quality gates. We are now standing on a solid foundation, ready to build features upward.

**Overall Goal**: To gradually evolve Trans-Hub from a powerful **core library** into a **flexible, easy-to-use tool**, ultimately becoming a **deployable, observable production-grade service**.

### **Phase One: Performance and Core Optimization - [✅ Completed]**

#### **🎯 Goal**

Complete performance optimization of the core library to ensure its performance in high-concurrency scenarios.

#### **✅ [Completed] Task 1.1: Optimize Database Write Performance**

*   **Results**: The `ensure_pending_translations` method in `persistence.py` has been refactored to utilize the `INSERT ... ON CONFLICT` (UPSERT) syntax, significantly improving write performance and atomicity.

### **Phase Two: Tooling & Observability - [🚀 Current Stage]**

#### **🎯 Goal**

Package the core library into a fully functional command-line tool with a good user experience, and establish a complete observability system to achieve the project's first "implementation.

#### **⏳ [To Do] Task 2.1: Build Command Line Interface (CLI)**

*   **Subtask 2.1.1**: **Create CLI Module and Dependency Assembly**
    *   **Action**: Create `trans_hub/cli/main.py`, import `typer`. Create a `_setup_coordinator()` helper function responsible for all dependencies' "manual DI" process.
*   **Subtask 2.1.2**: **Implement Core CLI Commands**
    *   **Action**: Create core commands such as `request`, `process`, `gc`, and consider using the `rich` library to provide clear, formatted output.
*   **Subtask 2.1.3**: **Implement DLQ Management Commands**
    *   **Action**: Add methods like `replay_from_dlq`, `count_dlq`, `clear_dlq` in `Coordinator` and `PersistenceHandler`. Create subcommands like `dlq replay` and `dlq show` in the CLI.
*   **Deliverable**: A fully functional, user-friendly operational tool that can be directly used with the `trans-hub` command.

#### **⏳ [To-Do] Task 2.2: Establish Observability (Metrics)**

*   **Subtask 2.2.1**: **Define the `MetricsRecorder` interface and implementation**
    *   **Action**: Define the `MetricsRecorder` protocol in `interfaces.py`. Create `trans_hub/metrics.py` and implement `PrometheusMetricsRecorder` and `NoOpMetricsRecorder`.
*   **Subtask 2.2.2**: **Apply metrics using the decorator pattern**
    *   **Action**: Create `MetricsPolicyDecorator` in `policies.py`, which wraps a real `ProcessingPolicy` instance and records key metrics (such as processing count, time taken, cache hit rate, etc.) before and after the `process_batch` call.
*   **Subtask 2.2.3**: **Assemble at the CLI entry point**
    *   **Action**: In the `_setup_coordinator` function, decide based on the configuration whether to use `PrometheusMetricsRecorder` or `NoOpMetricsRecorder` to wrap `DefaultProcessingPolicy`.
*   **Deliverable**: A fully decoupled, pluggable monitoring system that lays the foundation for performance monitoring and alerting.

#### **⏳ [To Do] Task 2.3: Improve Configuration and Logging**

*   **Subtask 2.3.1**: **Enhance the runtime configuration capability of logs**
    *   **Action**: Add `--log-level` and `--log-format` options to the CLI, allowing users to override default configurations at runtime, greatly improving the convenience of debugging and operations.
*   **Deliverable**: An application with more flexible and easier-to-debug logging behavior.

### **Phase Three: Servitization & Deployment**

#### **🎯 Goal**

Expose the capabilities of Trans-Hub through the network, making it a deployable, easily configurable, and monitorable microservice.

#### **⏳ [To Do] Task 3.1: Package as Web API Service**

*   **Subtask 3.1.1**: **Create server module with FastAPI dependency injection**
    *   **Action**: Create `trans_hub/server/main.py`. Rewrite the logic of `_setup_coordinator` using FastAPI's `Depends` mechanism to achieve request-level dependency injection and application lifecycle management.
*   **Subtask 3.1.2**: **Implement API endpoints**
    *   **Action**: Create RESTful API routes corresponding to CLI functions such as `POST /request`, `POST /process-jobs`, `GET /metrics`, etc.
*   **Subtask 3.1.3**: **Containerization**
    *   **Action**: Write a `Dockerfile` to package the application into an image and provide a `docker-compose.yml` for one-click local service startup.
*   **Deliverable**: A fully service-oriented, deployable, and monitorable instance of Trans-Hub.

### **Phase Four: Ecosystem & Community**

#### **🎯 Goal**

Transform Trans-Hub into an open-source project with a good ecosystem, easy to expand and contribute to.

#### **⏳ [Future] Task 4.1: Establish a Plugin-Based Engine System**

*   **Action**: Explore expanding the engine discovery mechanism from "in-package discovery" to support dynamically loading third-party engine packages through `entry_points`, allowing the community to easily develop and share custom engines.

#### **⏳ [Future] Task 4.2: Improve Developer and User Documentation**

*   **Action**: Create a formal documentation website (such as using `MkDocs` or `Sphinx`), providing detailed architecture descriptions, API references, contribution guidelines, and usage tutorials.

</details>

<details>
<summary><strong>简体中文</strong></summary>

### **Trans-Hub 统一开发路线图 (v2.2 最终版)**

**当前状态**: 核心库的**第一阶段：性能与核心优化**已全面完成 (`v3.0.0` 阶段性目标达成)。代码库质量稳定、架构清晰、性能得到优化，100% 通过所有质量门禁。我们现在站在一个坚实的地基上，准备向上构建功能。

**总体目标**: 将 Trans-Hub 从一个强大的**核心库**，逐步演进为一个**配置灵活、易于使用的工具**，最终成为一个**可独立部署、可观测的生产级服务**。

### **第一阶段：性能与核心优化 - [✅ 已完成]**

#### **🎯 目标**

完成对核心库的性能优化，确保其在高并发场景下的表现。

#### **✅ [已完成] 任务 1.1: 优化数据库写入性能**

*   **成果**: `persistence.py` 中的 `ensure_pending_translations` 方法已重构，利用 `INSERT ... ON CONFLICT` (UPSERT) 语法，显著提升了写入性能和原子性。

### **第二阶段：工具化与可观测性 (Tooling & Observability) - [🚀 当前阶段]**

#### **🎯 目标**

将核心库封装成一个功能完备、用户体验良好的命令行工具，并建立完整的可观测性体系，实现项目的首次“落地”。

#### **⏳ [待办] 任务 2.1: 构建命令行接口 (CLI)**

*   **子任务 2.1.1**: **创建 CLI 模块与依赖装配**
    *   **动作**: 创建 `trans_hub/cli/main.py`，引入 `typer`。创建一个 `_setup_coordinator()` 辅助函数，负责所有依赖的“手动 DI”过程。
*   **子任务 2.1.2**: **实现核心 CLI 命令**
    *   **动作**: 创建 `request`, `process`, `gc` 等核心命令，并考虑利用 `rich` 库提供清晰的、带格式的输出。
*   **子任务 2.1.3**: **实现 DLQ 管理命令**
    *   **动作**: 在 `Coordinator` 和 `PersistenceHandler` 中添加 `replay_from_dlq`, `count_dlq`, `clear_dlq` 等方法。在 CLI 中创建 `dlq replay` 和 `dlq show` 等子命令。
*   **交付成果**: 一个可通过 `trans-hub` 命令直接使用的、功能完备、交互友好的运维工具。

#### **⏳ [待办] 任务 2.2: 建立可观测性 (Metrics)**

*   **子任务 2.2.1**: **定义 `MetricsRecorder` 接口与实现**
    *   **动作**: 在 `interfaces.py` 中定义 `MetricsRecorder` 协议。创建 `trans_hub/metrics.py`，并实现 `PrometheusMetricsRecorder` 和 `NoOpMetricsRecorder`。
*   **子任务 2.2.2**: **通过装饰器模式应用指标**
    *   **动作**: 在 `policies.py` 中创建 `MetricsPolicyDecorator`，它包裹一个真实的 `ProcessingPolicy` 实例，并在 `process_batch` 调用前后记录关键指标（如处理计数、耗时、缓存命中率等）。
*   **子任务 2.2.3**: **在 CLI 入口处装配**
    *   **动作**: 在 `_setup_coordinator` 函数中，根据配置决定是使用 `PrometheusMetricsRecorder` 还是 `NoOpMetricsRecorder` 来包裹 `DefaultProcessingPolicy`。
*   **交付成果**: 一套完全解耦、可插拔的监控系统，为性能监控和告警打下基础。

#### **⏳ [待办] 任务 2.3: 完善配置与日志**

*   **子任务 2.3.1**: **增强日志的运行时配置能力**
    *   **动作**: 为 CLI 添加 `--log-level` 和 `--log-format` 选项，允许用户在运行时覆盖默认配置，极大提升调试和运维的便利性。
*   **交付成果**: 一个日志行为更灵活、更易于调试的应用程序。

### **第三阶段：服务化与部署 (Servitization & Deployment)**

#### **🎯 目标**

将 Trans-Hub 的能力通过网络暴露，使其成为一个可独立部署、易于配置和监控的微服务。

#### **⏳ [待办] 任务 3.1: 封装为 Web API 服务**

*   **子任务 3.1.1**: **创建服务器模块与 FastAPI 依赖注入**
    *   **动作**: 创建 `trans_hub/server/main.py`。将 `_setup_coordinator` 的逻辑，用 FastAPI 的 `Depends` 机制重写，实现请求级别的依赖注入和应用生命周期管理。
*   **子任务 3.1.2**: **实现 API 端点**
    *   **动作**: 创建 `POST /request`, `POST /process-jobs`, `GET /metrics` 等与 CLI 功能对应的 RESTful API 路由。
*   **子任务 3.1.3**: **容器化**
    *   **动作**: 编写 `Dockerfile` 将应用打包成镜像，并提供 `docker-compose.yml` 用于本地一键启动服务。
*   **交付成果**: 一个完全服务化的、可部署、可监控的 Trans-Hub 实例。

### **第四阶段：生态与社区 (Ecosystem & Community)**

#### **🎯 目标**

将 Trans-Hub 打造为一个拥有良好生态、易于扩展和贡献的开源项目。

#### **⏳ [未来] 任务 4.1: 建立插件化引擎系统**

*   **动作**: 探索将引擎发现机制从“包内发现”扩展为支持通过 `entry_points` 动态加载第三方引擎包，让社区可以轻松开发和分享自定义引擎。

#### **⏳ [未来] 任务 4.2: 完善开发者与用户文档**

*   **动作**: 创建一个正式的文档网站（如使用 `MkDocs` 或 `Sphinx`），提供详尽的架构说明、API 参考、贡献指南和使用教程。

</details>
