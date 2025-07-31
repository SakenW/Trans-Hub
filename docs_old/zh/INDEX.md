# **Trans-Hub 文档库**

欢迎来到 `Trans-Hub` 的官方文档库。本库旨在为不同类型的读者——无论是初次使用的用户、希望贡献代码的开发者，还是项目的核心维护者——提供清晰、准确且易于查找的信息。

## **文档结构与设计哲学**

我们的文档库遵循**基于受众和目的**的设计原则进行组织。这意味着每个目录和文件都有其明确的目标读者和内容范围，以最大限度地减少信息重叠，并确保“单一事实来源”。

---

## **可运行的示例 (Examples)**

我们相信“代码是最好的文档”。在 `/examples` 目录下，我们提供了一系列可以直接运行的、注释详尽的 Python 脚本，它们旨在直观地展示 `Trans-Hub` 的核心功能和最佳实践。

- **[基础用法 (`01_basic_usage.py`)](../examples/01_basic_usage.py)**: 快速入门的最佳起点，演示了核心的请求-处理-缓存流程。
- **[真实世界模拟 (`02_real_world_simulation.py`)](../examples/02_real_world_simulation.py)**: 终极演示，在一个复杂的并发环境中展示了 `Trans-Hub` 的所有高级功能。
- **[特定用例：翻译 `.strings` 文件 (`03_specific_use_case_strings_file.py`)](../examples/03_specific_use_case_strings_file.py)**: 展示了如何将 `Trans-Hub` 集成到具体的本地化工作流中。

在深入阅读详细指南之前，我们强烈建议您先亲手运行这些示例。

---

## **文档导航**

### **1. 指南 (Guides)**

如果您想系统地学习 `Trans-Hub` 的概念和用法，请从这里开始。

- **[指南 1：快速入门](./guides/01_quickstart.md)**
  - **内容**: `Trans-Hub` 的安装和最核心的工作流的文字说明。
  - **目标读者**: 所有人。

- **[指南 2：高级用法](./guides/02_advanced_usage.md)**
  - **内容**: 对 `business_id` vs `context` 的深入辨析，以及如何激活高级引擎、管理数据生命周期和与 Web 框架集成的说明。
  - **目标读者**: 进阶开发者。

- **[指南 3：配置深度解析](./guides/03_configuration.md)**
  - **内容**: `TransHubConfig` 及其所有子模型的权威参考，详细解释了每个配置项的作用以及如何通过环境变量进行设置。
  - **目标读者**: 所有用户。

- **[指南 4：部署与运维](./guides/04_deployment.md)**
  - **内容**: 在生产环境中部署和维护 `Trans-Hub` 的最佳实践，包括数据库迁移、后台 Worker 模式和 GC 调度。
  - **目标读者**: 运维工程师和需要在生产环境中使用 `Trans-Hub` 的开发者。

---

### **2. API 参考 (API Reference)**

这里是 `Trans-Hub` 所有公共接口和数据结构的权威定义。

- **[核心类型 (Core Types)](./api/core_types.md)**
- **[`Coordinator` API](./api/coordinator.md)**
- **[`PersistenceHandler` 接口](./api/persistence_handler.md)**

---

### **3. 架构 (Architecture)**

如果您想深入了解 `Trans-Hub` 的“引擎盖下”是如何工作的。

- **[架构概述](./architecture/01_overview.md)**
- **[数据模型与数据库设计](./architecture/02_data_model.md)**

---

### **4. 贡献 (Contributing)**

欢迎您为 `Trans-Hub` 社区做出贡献！

- **[指南：开发一个新引擎](./contributing/developing_engines.md)**

---

## **文档编写规范**

为了保持文档库的一致性和高质量，所有未来的文档编写都应遵循以下原则：

1.  **遵循既定结构**: 新的文档应根据其内容和目标读者，放置在上述四个目录之一。
2.  **保持单一事实来源**: API 和架构的定义应始终位于 `/api` 和 `/architecture` 目录。其他文档应**链接**到它们，而不是重复内容。
3.  **提供可运行的示例**: 在 `/guides` 中提供的代码示例应尽可能完整和可直接运行。
4.  **更新变更日志**: 对代码或文档的重大变更，都应在项目根目录的 `CHANGELOG.md` 中进行记录。
