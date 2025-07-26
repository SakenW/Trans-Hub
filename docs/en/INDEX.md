# **Trans-Hub Document Library**

Welcome to the official documentation repository of `Trans-Hub`. This repository aims to provide clear, accurate, and easily accessible information for different types of readers—whether they are first-time users, developers looking to contribute code, or core maintainers of the project.

## **Document Structure and Design Philosophy**

Our document library is organized according to the design principles of **audience and purpose**. This means that each directory and file has its specific target audience and content scope, minimizing information overlap and ensuring a 'single source of truth'.

---

## **可运行的示例 (Examples)**

我们相信“代码是最好的文档”。在 `/examples` 目录下，我们提供了一系列可以直接运行的、注释详尽的 Python 脚本，它们旨在直观地展示 `Trans-Hub` 的核心功能和最佳实践。

- **[基础用法 (`01_basic_usage.py`)](../examples/01_basic_usage.py)**: 快速入门的最佳起点，演示了核心的请求-处理-缓存流程。
- **[真实世界模拟 (`02_real_world_simulation.py`)](../examples/02_real_world_simulation.py)**: 终极演示，在一个复杂的并发环境中展示了 `Trans-Hub` 的所有高级功能。
- **[特定用例：翻译 `.strings` 文件 (`03_specific_use_case_strings_file.py`)](../examples/03_specific_use_case_strings_file.py)**: 展示了如何将 `Trans-Hub` 集成到具体的本地化工作流中。

在深入阅读详细指南之前，我们强烈建议您先亲手运行这些示例。

---

## **Document Navigation**

### **1. Guides**

If you want to systematically learn the concepts and usage of `Trans-Hub`, please start here.

- **[Guide 1: Quick Start](./guides/01_quickstart.md)**
  - **Content**: Text description of the installation of `Trans-Hub` and the most core workflow.
  - **Target Audience**: Everyone.

- **[Guide 2: Advanced Usage](./guides/02_advanced_usage.md)**
  - **Content**: An in-depth analysis of `business_id` vs `context`, as well as instructions on how to activate the advanced engine, manage data lifecycle, and integrate with web frameworks.
  - **Target Audience**: Advanced developers.

- **[Guide 3: Configuration Deep Dive](./guides/03_configuration.md)**
  - **Content**: An authoritative reference for `TransHubConfig` and all its sub-models, detailing the function of each configuration item and how to set them via environment variables.
  - **Target Audience**: All users.

- **[Guide 4: Deployment and Operations](./guides/04_deployment.md)**
  - **Content**: Best practices for deploying and maintaining `Trans-Hub` in a production environment, including database migration, background worker mode, and GC scheduling.
  - **Target Audience**: Operations engineers and developers who need to use `Trans-Hub` in a production environment.

---

### **2. API 参考 (API Reference)**

这里是 `Trans-Hub` 所有公共接口和数据结构的权威定义。

- **[核心类型 (Core Types)](./api/core_types.md)**
- **[`Coordinator` API](./api/coordinator.md)**
- **[`PersistenceHandler` 接口](./api/persistence_handler.md)**

---

### **3. Architecture**

If you want to learn more about how `Trans-Hub` works under the hood.

- **[Architecture Overview](./architecture/01_overview.md)**
- **[Data Model and Database Design](./architecture/02_data_model.md)**

---

### **4. 贡献 (Contributing)**

欢迎您为 `Trans-Hub` 社区做出贡献！

- **[指南：开发一个新引擎](./contributing/developing_engines.md)**

---

## **Document Writing Standards**

To maintain the consistency and high quality of the document library, all future document writing should adhere to the following principles:

1. **Follow the established structure**: New documents should be placed in one of the four directories above based on their content and target audience.  
2. **Maintain a single source of truth**: Definitions of APIs and architectures should always be located in the `/api` and `/architecture` directories. Other documents should **link** to them instead of duplicating content.  
3. **Provide runnable examples**: Code examples provided in `/guides` should be as complete and directly runnable as possible.  
4. **Update the changelog**: Significant changes to code or documentation should be recorded in the `CHANGELOG.md` in the project root directory.
