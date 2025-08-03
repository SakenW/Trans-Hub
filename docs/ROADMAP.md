**当前状态**: 核心库的**第一阶段：性能与核心优化**已全面完成 (`v3.0.0` 阶段性目标达成)。代码库质量稳定、架构清晰、性能得到优化，100% 通过所有质量门禁。我们现在站在一个坚实的地基上，准备向上构建功能。

# Trans-Hub 项目路线图

**总体目标**: 将 Trans-Hub 从一个强大的**核心库**，逐步演进为一个**配置灵活、易于使用的工具**，最终成为一个**可独立部署、可观测的生产级服务**。

---

## **第一阶段：性能与核心优化 - [✅ 已完成]**

### **🎯 第一阶段目标**
完成对核心库的性能优化，确保其在高并发场景下的表现。

---

#### **✅ [已完成] 任务 1.1: 优化数据库写入性能**
*   **成果**: `persistence.py` 中的 `ensure_pending_translations` 方法已重构，利用 `INSERT ... ON CONFLICT` (UPSERT) 语法，显著提升了写入性能和原子性。

---

## **第二阶段：工具化与可观测性 (Tooling & Observability) - [🚀 当前阶段]**

### **🎯 第二阶段目标**
将核心库封装成一个功能完备、用户体验良好的命令行工具，并建立完整的可观测性体系，实现项目的首次“落地”。

---

#### **⏳ [待办] 任务 2.1: 构建命令行接口 (CLI)**
*   **子任务 2.1.1**: **创建 CLI 模块与依赖装配**
    *   **动作**: 创建 `trans_hub/cli/main.py`，引入 `typer`。创建一个 `_setup_coordinator()` 辅助函数，负责所有依赖的“手动 DI”过程。
*   **子任务 2.1.2**: **实现核心 CLI 命令**
    *   **动作**: 创建 `request`, `process`, `gc` 等核心命令，并考虑利用 `rich` 库提供清晰的、带格式的输出。
*   **子任务 2.1.3**: **实现 DLQ 管理命令**
    *   **动作**: 在 `Coordinator` 和 `PersistenceHandler` 中添加 `replay_from_dlq`, `count_dlq`, `clear_dlq` 等方法。在 CLI 中创建 `dlq replay` 和 `dlq show` 等子命令。
*   **交付成果**: 一个可通过 `trans-hub` 命令直接使用的、功能完备、交互友好的运维工具。

---

#### **⏳ [待办] 任务 2.2: 建立可观测性 (Metrics)**
*   **子任务 2.2.1**: **定义 `MetricsRecorder` 接口与实现**
    *   **动作**: 在 `interfaces.py` 中定义 `MetricsRecorder` 协议。创建 `trans_hub/metrics.py`，并实现 `PrometheusMetricsRecorder` 和 `NoOpMetricsRecorder`。
*   **子任务 2.2.2**: **通过装饰器模式应用指标**
    *   **动作**: 在 `policies.py` 中创建 `MetricsPolicyDecorator`，它包裹一个真实的 `ProcessingPolicy` 实例，并在 `process_batch` 调用前后记录关键指标（如处理计数、耗时、缓存命中率等）。
*   **子任务 2.2.3**: **在 CLI 入口处装配**
    *   **动作**: 在 `_setup_coordinator` 函数中，根据配置决定是使用 `PrometheusMetricsRecorder` 还是 `NoOpMetricsRecorder` 来包裹 `DefaultProcessingPolicy`。
*   **交付成果**: 一套完全解耦、可插拔的监控系统，为性能监控和告警打下基础。

---

#### **⏳ [待办] 任务 2.3: 完善配置与日志**
*   **子任务 2.3.1**: **增强日志的运行时配置能力**
    *   **动作**: 为 CLI 添加 `--log-level` 和 `--log-format` 选项，允许用户在运行时覆盖默认配置，极大提升调试和运维的便利性。
*   **交付成果**: 一个日志行为更灵活、更易于调试的应用程序。

---

## **第三阶段：服务化与部署 (Servitization & Deployment)**

### **🎯 第三阶段目标**
将 Trans-Hub 的能力通过网络暴露，使其成为一个可独立部署、易于配置和监控的微服务。

---

#### **⏳ [待办] 任务 3.1: 封装为 Web API 服务**
*   **子任务 3.1.1**: **创建服务器模块与 FastAPI 依赖注入**
    *   **动作**: 创建 `trans_hub/server/main.py`。将 `_setup_coordinator` 的逻辑，用 FastAPI 的 `Depends` 机制重写，实现请求级别的依赖注入和应用生命周期管理。
*   **子任务 3.1.2**: **实现 API 端点**
    *   **动作**: 创建 `POST /request`, `POST /process-jobs`, `GET /metrics` 等与 CLI 功能对应的 RESTful API 路由。
*   **子任务 3.1.3**: **容器化**
    *   **动作**: 编写 `Dockerfile` 将应用打包成镜像，并提供 `docker-compose.yml` 用于本地一键启动服务。
*   **交付成果**: 一个完全服务化的、可部署、可监控的 Trans-Hub 实例。

---

## **第四阶段：生态与社区 (Ecosystem & Community)**

### **🎯 第四阶段目标**
将 Trans-Hub 打造为一个拥有良好生态、易于扩展和贡献的开源项目。

---

#### **⏳ [未来] 任务 4.1: 建立插件化引擎系统**
*   **动作**: 探索将引擎发现机制从“包内发现”扩展为支持通过 `entry_points` 动态加载第三方引擎包，让社区可以轻松开发和分享自定义引擎。

---

#### **⏳ [未来] 任务 4.2: 完善开发者与用户文档**
*   **动作**: 创建一个正式的文档网站（如使用 `MkDocs` 或 `Sphinx`），提供详尽的架构说明、API 参考、贡献指南和使用教程。