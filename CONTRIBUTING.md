<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->


<!-- English -->
# **Contribute to `Trans-Hub`**

<!-- 简体中文 -->
# **为 `Trans-Hub` 做出贡献**

---


[![Python CI/CD Pipeline](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/SakenW/trans-hub/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/SakenW/trans-hub)
[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<!-- English -->
We warmly welcome and thank you for your interest in contributing to `Trans-Hub`! Whether it's reporting bugs, submitting feature requests, or directly contributing code, every effort you make is crucial to us. ❤️

<!-- 简体中文 -->
我们非常欢迎并感谢您有兴趣为 `Trans-Hub` 做出贡献！无论是报告 bug、提交功能请求，还是直接贡献代码，您的每一份努力都对我们至关重要。❤️

---


<!-- English -->
## **Table of Contents**

<!-- 简体中文 -->
## **目录**

---


<!-- English -->
- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [General Development Guidelines](#general-development-guidelines)
- [Codebase Structure Overview](#codebase-structure-overview)
- [Environment Setup](#environment-setup)
- [Local Checklist Before Submission](#local-checklist-before-submission)
- [Submit Pull Request](#submit-pull-request)
- [Versioning Strategy](#versioning-strategy)
- [Release Process](#release-process)
- [Appendix: Detailed Development Guidelines](#appendix-detailed-development-guidelines)
  - [Language and Communication](#language-and-communication)
  - [Code Style and Quality](#code-style-and-quality)
  - [Architecture and Design](#architecture-and-design)
  - [Engine Development Guidelines](#engine-development-guidelines)
  - [Testing](#testing)
  - [Other Key Agreements](#other-key-agreements)

<!-- 简体中文 -->
- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发规范总则](#开发规范总则)
- [代码库结构概览](#代码库结构概览)
- [环境设置](#环境设置)
- [提交前的本地检查清单](#提交前的本地检查清单)
- [提交 Pull Request](#提交-pull-request)
- [版本号策略](#版本号策略)
- [发布流程](#发布流程)
- [附录：详细开发规范](#附录详细开发规范)
  - [语言与沟通](#语言与沟通)
  - [代码风格与质量](#代码风格与质量)
  - [架构与设计](#架构与设计)
  - [引擎开发规范](#引擎开发规范)
  - [测试](#测试)
  - [其他关键约定](#其他关键约定)

---


<!-- English -->
## **Code of Conduct**

<!-- 简体中文 -->
## **行为准则**

---


<!-- English -->
To create an open and friendly community environment, we hope that all participants will adhere to our [**Code of Conduct**](./CODE_OF_CONDUCT.md).

<!-- 简体中文 -->
为了营造一个开放、友好的社区环境，我们希望所有参与者都能遵守我们的 [**行为准则 (Code of Conduct)**](./CODE_OF_CONDUCT.md)。

---


<!-- English -->
## **How to Contribute**

<!-- 简体中文 -->
## **如何贡献**

---


<!-- English -->
We welcome any form of contribution, including but not limited to:

<!-- 简体中文 -->
我们欢迎任何形式的贡献，包括但不限于：

---


<!-- English -->
- **Report a Bug** or **Submit a Feature Suggestion** (via [GitHub Issues](https://github.com/SakenW/trans-hub/issues)).
- **Improve Documentation**: Found a typo or something unclear? Submit a PR to improve it!
- **Write Code**: Fix bugs or implement new features.

<!-- 简体中文 -->
- **报告 Bug** 或 **提交功能建议** (通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues))。
- **完善文档**：发现拼写错误或不清晰之处？提交一个 PR 来改进它！
- **编写代码**：修复 Bug 或实现新功能。

---


<!-- English -->
## **General Principles of Development Specifications**

<!-- 简体中文 -->
## **开发规范总则**

---


<!-- English -->
Before starting any coding work, please be sure to carefully read the [Appendix: Detailed Development Specifications](#Appendix-Detailed-Development-Specifications) at the end of this document.

<!-- 简体中文 -->
**在开始任何代码工作之前，请务必仔细阅读本文档末尾的 [附录：详细开发规范](#附录详细开发规范)。**

---


<!-- English -->
Trans-Hub is a project with strict requirements for code quality, architectural clarity, and maintainability. All contributed code must strictly adhere to these standards. This ensures the project can develop healthily in the long term.

<!-- 简体中文 -->
`Trans-Hub` 是一个对代码质量、架构清晰度和可维护性有严格要求的项目。所有贡献的代码都必须严格遵守这些规范。这确保了项目能够长期健康发展。

---


<!-- English -->
## **Overview of Code Repository Structure**

<!-- 简体中文 -->
## **代码库结构概览**

---


<!-- English -->
To help you quickly familiarize yourself with the project, here are the core directories and the responsibilities of the key scripts within them:

<!-- 简体中文 -->
为了帮助您快速熟悉项目，以下是核心目录及其中关键脚本的职责说明：

---


<!-- English -->
- **`trans_hub/`**: **Core library code**. All runtime logic for the project is located here.

- **`tests/`**: **Automated tests**.

  - This directory contains all the test cases for the project (using `pytest`). The CI/CD pipeline will automatically run all tests in this directory.
    ```bash
    # Run the full test suite
    poetry run pytest
    ```
  - **`tests/diag/`**: Contains some standalone **diagnostic scripts**.
    - `check_env.py`: Specifically designed for quickly validating the configuration of the `.env` file. It is very useful when you encounter configuration issues related to the API Key.
      ```bash
      # Run the environment check script
      poetry run python tests/diag/check_env.py
      ```

- **`docs/`**: **Official documentation**. All user-facing guides, API references, and architectural documentation are stored here. Please read the [**Documentation Index (INDEX.md)**](./docs/INDEX.md) to understand its structure.

- **`examples/`**: **"Living" example code**.

  - `03_specific_use_case_strings_file.py` (formerly `translate_strings_file.py`): This is a **fully functional end-to-end demonstration**. It aims to visually and operationally showcase how to use the core features of `Trans-Hub` in a complex scenario for human users.
    ```bash
    # Run the complex workflow demonstration
    poetry run python examples/03_specific_use_case_strings_file.py
    ```

- **`tools/`**: **Developer tools**.
  - **`inspect_db.py`**: A specialized **database inspection command-line tool**. It can connect to any `Trans-Hub` database file and print its contents and interpretations in an easily understandable way, making it a powerful tool for debugging persistence issues.
    ```bash
    # Inspect the contents of the example database
    poetry run python tools/inspect_db.py path/to/your/database.db
    ```

<!-- 简体中文 -->
- **`trans_hub/`**: **核心库代码**。项目的所有运行时逻辑都在这里。

- **`tests/`**: **自动化测试**。

  - 这里存放了项目的所有测试用例（使用 `pytest`）。CI/CD 流水线会自动运行此目录下的所有测试。
    ```bash
    # 运行完整的测试套件
    poetry run pytest
    ```
  - **`tests/diag/`**: 包含一些独立的**诊断脚本**。
    - `check_env.py`: 专门用于快速验证 `.env` 文件配置。当您遇到与 API Key 相关的配置问题时，它非常有用。
      ```bash
      # 运行环境检查脚本
      poetry run python tests/diag/check_env.py
      ```

- **`docs/`**: **官方文档**。所有面向用户的指南、API 参考和架构文档都存放在这里。请先阅读 [**文档库索引 (INDEX.md)**](./docs/INDEX.md) 来了解其结构。

- **`examples/`**: **“活”的示例代码**。

  - `03_specific_use_case_strings_file.py` (旧名: `translate_strings_file.py`): 这是一个**端到端的、功能完善的演示**。它旨在向人类用户直观地、可运行地展示如何在一个复杂的场景中使用 `Trans-Hub` 的各项核心功能。
    ```bash
    # 运行复杂工作流演示
    poetry run python examples/03_specific_use_case_strings_file.py
    ```

- **`tools/`**: **开发者工具**。
  - **`inspect_db.py`**: 一个专业的**数据库检查命令行工具**。它能连接到任何 `Trans-Hub` 数据库文件，并以一种易于理解的方式将其内容和解读打印出来，是调试持久化问题的利器。
    ```bash
    # 检查示例数据库的内容
    poetry run python tools/inspect_db.py path/to/your/database.db
    ```

---


<!-- English -->
## **Environment Setup**

<!-- 简体中文 -->
## **环境设置**

---


<!-- English -->
1.  **Clone the repository**: `git clone https://github.com/SakenW/trans-hub.git && cd trans-hub`
2.  **Install Poetry**: Please ensure you have installed [Poetry](https://python-poetry.org/).
3.  **Install all dependencies**: `poetry install --with dev --with openai`
4.  **Configure environment variables**: Create your local `.env` file based on the `.env.example` template and fill in the necessary API keys to run the full test suite.
    ```bash
    cp .env.example .env
    ```
5.  **Run the test suite**: Before you start coding, please run `poetry run pytest` to ensure the local environment is working properly.

<!-- 简体中文 -->
1.  **克隆仓库**: `git clone https://github.com/SakenW/trans-hub.git && cd trans-hub`
2.  **安装 Poetry**: 请确保您已安装 [Poetry](https://python-poetry.org/)。
3.  **安装所有依赖**: `poetry install --with dev --with openai`
4.  **配置环境变量**:
    根据 `.env.example` 模板创建您的本地 `.env` 文件，并填入必要的 API 密钥以运行完整的测试套件。
    ```bash
    cp .env.example .env
    ```
5.  **运行测试套件**: 在开始编码前，请运行 `poetry run pytest` 确保本地环境正常。

---


<!-- English -->
## **Local Checklist Before Submission**

<!-- 简体中文 -->
## **提交前的本地检查清单**

---


<!-- English -->
Before you execute `git commit`, please make sure to run the following three commands locally to ensure your code meets the project's quality standards. This can prevent your Pull Request from being rejected due to CI/CD check failures after submission.

<!-- 简体中文 -->
在您执行 `git commit` 之前，请务必在本地运行以下三个命令，以确保您的代码符合项目的质量标准。这可以避免在提交 Pull Request 后因为 CI/CD 检查失败而被驳回。

---


<!-- English -->
1.  **Format Code**: Ensure all code styles are consistent.
    ```bash
    poetry run ruff format .
    ```
2.  **Code Quality and Style Check**: Automatically fix potential issues.
    ```bash
    poetry run ruff check --fix .
    ```
3.  **Static Type Checking**: Ensure there are no type errors.
    ```bash
    poetry run mypy .
    ```

<!-- 简体中文 -->
1.  **格式化代码**: 确保所有代码风格统一。
    ```bash
    poetry run ruff format .
    ```
2.  **代码质量与风格检查**: 自动修复潜在问题。
    ```bash
    poetry run ruff check --fix .
    ```
3.  **静态类型检查**: 确保没有类型错误。
    ```bash
    poetry run mypy .
    ```

---


<!-- English -->
> **Tip**: Running these commands frequently is a good habit.

<!-- 简体中文 -->
> **提示**: 频繁运行这些命令是个好习惯。

---


<!-- English -->
## **Submit Pull Request**

<!-- 简体中文 -->
## **提交 Pull Request**

---


<!-- English -->
1. After completing development and testing, create a Pull Request (PR) with the target branch as `main`.  
2. In the PR description, please clearly state what issue you have resolved or what feature you have implemented. We recommend using the [PR template](./.github/pull_request_template.md) provided by the project.  
3. Please ensure that your PR passes all automated checks in our CI pipeline.  
4. Project maintainers will review your code as soon as possible.

<!-- 简体中文 -->
1.  完成开发和测试后，创建一个 Pull Request (PR)，目标分支为 `main`。
2.  在 PR 的描述中，请清晰地说明您解决了什么问题或实现了什么功能。我们推荐使用项目提供的 [PR 模板](./.github/pull_request_template.md)。
3.  请确保您的 PR 通过了我们 CI 流水线的所有自动化检查。
4.  项目维护者会尽快审查您的代码。

---


<!-- English -->
## **Version Number Strategy**

<!-- 简体中文 -->
## **版本号策略**

---


<!-- English -->
This project follows the [**Semantic Versioning 2.0.0**](https://semver.org/lang/zh-CN/) specification. The version number format is `major.minor.patch` (for example, `2.4.1`), with the following rules:

<!-- 简体中文 -->
本项目遵循 [**语义化版本 2.0.0 (Semantic Versioning)**](https://semver.org/lang/zh-CN/) 规范。版本号格式为 `主版本号.次版本号.修订号` (例如 `2.4.1`)，规则如下：

---


<!-- English -->
### **Major Version Number (MAJOR)**

<!-- 简体中文 -->
### **主版本号 (MAJOR)**

---


<!-- English -->
Increase only when you make **incompatible API changes**. This usually means that users' code needs to be modified to accommodate the new version.

<!-- 简体中文 -->
仅当您做了**不兼容的 API 修改**时增加。这通常意味着用户的代码需要修改才能适应新版本。

---


<!-- English -->
- **Applicable Scenarios**:
  - A public function/class has been renamed or removed.
  - Function parameters have changed, causing old calling methods to fail.
  - Non-backward compatible changes have been made to the database structure.

<!-- 简体中文 -->
- **适用场景**:
  - 重命名或移除了一个公开的函数/类。
  - 更改了函数参数，导致旧的调用方式失效。
  - 做了不向后兼容的数据库结构变更。

---


<!-- English -->
### **Minor Version Number (MINOR)**

<!-- 简体中文 -->
### **次版本号 (MINOR)**

---


<!-- English -->
Add when you increase new features in a backward-compatible way. Users can safely upgrade and selectively use new features.

<!-- 简体中文 -->
当您以**向后兼容的方式增加新功能**时增加。用户可以安全升级，并选择性地使用新功能。

---


<!-- English -->
- **Applicable Scenarios**:
  - Add a new translation engine.
  - Add new optional parameters (such as `force_retranslate`) to existing functions.
  - Introduce new mechanisms such as dead letter queues or observability metrics.

<!-- 简体中文 -->
- **适用场景**:
  - 增加一个新的翻译引擎。
  - 为现有函数增加新的、可选的参数（如 `force_retranslate`）。
  - 引入死信队列或可观测性指标等新机制。

---


<!-- English -->
### **Revision Number (PATCH)**

<!-- 简体中文 -->
### **修订号 (PATCH)**

---


<!-- English -->
Increase when you make **backward compatibility issue fixes**. This usually involves fixing bugs or improving performance, and users should always be able to upgrade safely.

<!-- 简体中文 -->
当您做了**向后兼容的问题修正**时增加。这通常是修复 Bug 或提升性能，用户应该总是可以安全地升级。

---


<!-- English -->
- **Applicable Scenarios**:
  - Fixed a concurrency safety vulnerability.
  - Corrected an error in the garbage collection logic.
  - Updated third-party dependencies with security vulnerabilities.

<!-- 简体中文 -->
- **适用场景**:
  - 修复了一个并发安全漏洞。
  - 修正了垃圾回收逻辑中的一个错误。
  - 更新了有安全漏洞的第三方依赖。

---


<!-- English -->
## **Release Process**

<!-- 简体中文 -->
## **发布流程**

---


<!-- English -->
> 🚨 **Note**: This section is only applicable to the core maintainers of the project.

<!-- 简体中文 -->
> 🚨 **注意**: 此部分仅适用于项目的核心维护者。

---


<!-- English -->
This project follows a strict and detailed standard operating procedure (SOP) for version releases to ensure the quality and reliability of each version.

<!-- 简体中文 -->
本项目遵循一套严格、详细的标准作业流程（SOP）来进行版本发布，以确保每个版本的质量和可靠性。

---


<!-- English -->
👉 **[Click here to view the complete release standard operating procedure (SOP)](./RELEASE_SOP.md)**

<!-- 简体中文 -->
👉 **[点击这里查看完整的发布标准作业流程 (SOP)](./RELEASE_SOP.md)**

---


<!-- English -->
## **Appendix: Detailed Development Specifications**

<!-- 简体中文 -->
## **附录：详细开发规范**

---


<!-- English -->
This section is the detailed technical specifications that all contributors must adhere to.

<!-- 简体中文 -->
本节是所有贡献者必须遵守的详细技术规范。

---


<!-- English -->
### **Language and Communication**

<!-- 简体中文 -->
### **语言与沟通**

---


<!-- English -->
1.  **Language in Code:**
    - **Comments, Docstrings, Log Information, User-visible Strings:** **Must all be in Chinese**.
    - **Variable/Function/Class Names and Other Code Identifiers:** **Must be in English** and follow PEP 8 naming conventions.
2.  **Language for Communication Tools:**
    - **All Conversations:** **Default to Chinese**.
    - **AI Prompt:** Can be in English.

<!-- 简体中文 -->
1.  **代码内语言:**
    - **注释、文档字符串 (Docstrings)、日志信息、用户可见字符串:** **必须全部使用中文**。
    - **变量/函数/类名等代码标识符:** **必须使用英文**，并遵循 PEP 8 命名约定。
2.  **沟通工具语言:**
    - **所有对话:** **默认使用中文**。
    - **AI Prompt:** 可以使用英文。

---


<!-- English -->
### **Code Style and Quality**

<!-- 简体中文 -->
### **代码风格与质量**

---


<!-- English -->
1.  **Formatting:** Strictly follow `PEP 8`, use `ruff format`, with a line length limit of 88 characters.  
2.  **Static Checks:**  
    - **Linter:** Use `ruff`, configuration can be found in `pyproject.toml`.  
    - **Type Checking:** Use `mypy`, new code must have complete type annotations.  
3.  **Logging Standards:**  
    - **Must use `structlog`**, `print()` is prohibited for debugging.  
    - Fully utilize context binding features.  
    - Strictly adhere to logging level semantics (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). `ERROR` and above levels must include `exc_info=True`.  
4.  **File Header Standards:**  
    - The first line of all `.py` files must be a comment identifying its full path, such as `# trans_hub/coordinator.py`.  
    - **Prohibited** to add informal status descriptions like `(revised)` at the file header.  
    - Docstrings (`"""..."""`) **are only for** describing the current functionality of the module, **prohibited** from including any change history. The only place for change records is **Git commit messages** and **`CHANGELOG.md`**.  
5.  **Handling Linter Rule Exceptions (`# noqa`):**  
    -   **Principle:** We strive for 100% compliance with `ruff` rules. However, in rare cases, specific functionality or code readability may necessitate local rule disabling.  
    -   **Usage:** Must use line-level comments `# noqa: <RuleCode>`, and it is encouraged to provide a brief reason. Misuse of `# noqa` is not allowed.  
    -   **Example 1 (`E402`):** In tools or example scripts, to ensure proper import of project modules, we may need to `import` after modifying `sys.path`. This violates the `E402` rule (module-level imports not at the top of the file).  
        ```python
        import sys
        sys.path.insert(0, ...)
        
        # Must import after modifying the path, so we ignore E402
        from trans_hub import Coordinator  # noqa: E402
        ```  
    -   **Example 2 (`N806`):** When dynamically creating classes using techniques like `pydantic.create_model`, we assign the returned class to a variable in `PascalCase` style. This triggers the `N806` rule (function variables should be lowercase). To maintain clarity of code intent (it is a class), we exempt this rule.  
        ```python
        # The variable name is intentionally in PascalCase because it is a dynamically created class
        DynamicClassName = create_model(...)  # noqa: N806
        ```

<!-- 简体中文 -->
1.  **格式化:** 严格遵循 `PEP 8`，使用 `ruff format`，行长限制为 88 字符。
2.  **静态检查:**
    - **Linter:** 使用 `ruff`，配置见 `pyproject.toml`。
    - **类型检查:** 使用 `mypy`，新代码必须有完整的类型注解。
3.  **日志规范:**
    - **必须使用 `structlog`**，禁止 `print()` 用于调试。
    - 充分利用上下文绑定功能。
    - 严格遵循日志级别语义（`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`）。`ERROR` 及以上级别必须附带 `exc_info=True`。
4.  **文件头规范:**
    - 所有 `.py` 文件第一行必须是标识其完整路径的注释，如 `# trans_hub/coordinator.py`。
    - **严禁**在文件头添加 `(修正版)` 等非正式状态描述。
    - 文档字符串（`"""..."""`）**只用于**描述模块的当前功能，**严禁**包含任何变更历史。变更记录的唯一归宿是 **Git 提交信息**和 **`CHANGELOG.md`**。
5.  **处理 Linter 规则例外 (`# noqa`):**
    -   **原则**: 我们力求代码 100% 符合 `ruff` 的规则。但在极少数情况下，为了实现特定功能或保持代码可读性，可以局部禁用某条规则。
    -   **用法**: 必须使用行级注释 `# noqa: <RuleCode>`，并鼓励附上简要的原因说明。滥用 `# noqa` 是不被允许的。
    -   **示例 1 (`E402`)**: 在工具或示例脚本中，为了确保能正确导入项目模块，我们可能需要在修改 `sys.path` 之后再进行 `import`。这会违反 `E402` 规则（模块级导入不在文件顶部）。
        ```python
        import sys
        sys.path.insert(0, ...)
        
        # 必须在修改路径后导入，因此我们忽略 E402
        from trans_hub import Coordinator  # noqa: E402
        ```
    -   **示例 2 (`N806`)**: 在使用 `pydantic.create_model` 等技术动态创建类时，我们会将返回的类赋值给一个 `PascalCase` 风格的变量。这会触发 `N806` 规则（函数内变量应为小写）。为了保持代码意图的清晰（它是一个类），我们豁免此规则。
        ```python
        # 变量名使用 PascalCase 是故意的，因为它是一个动态创建的类
        DynamicClassName = create_model(...)  # noqa: N806
        ```

---


<!-- English -->
### **Architecture and Design**

<!-- 简体中文 -->
### **架构与设计**

---


<!-- English -->
1.  **Single Responsibility Principle (SRP):** Each module, class, or function should do one thing only.  
2.  **Dependency Inversion Principle (DIP):** Core logic depends on abstractions (`Protocol`), not on concrete implementations.  
3.  **Configuration Separation:** Hard coding is strictly prohibited. All configuration items must be defined in `config.py` and loaded via `pydantic-settings`.  
4.  **Pure Asynchronous First:** Core workflows must be asynchronous. Any blocking calls **must be wrapped with `asyncio.to_thread`**.  
5.  **Correct Use of Core Concepts:** Contributed code must correctly use core concepts such as `business_id` and `context`. For their usage scenarios and best practices, please refer to the [**Advanced Usage Guide**](./docs/guides/02_advanced_usage.md).  
6.  **Performance-First Database Design:** All database-related code and schema changes must follow performance best practices. For detailed specifications, please refer to [**Data Model and Database Design**](./docs/architecture/02_data_model.md).

<!-- 简体中文 -->
1.  **单一职责原则 (SRP):** 每个模块、类、函数只做一件事。
2.  **依赖倒置原则 (DIP):** 核心逻辑依赖抽象（`Protocol`），而非具体实现。
3.  **配置分离:** 严禁硬编码。所有配置项必须在 `config.py` 中定义，并通过 `pydantic-settings` 加载。
4.  **纯异步优先:** 核心工作流必须异步。任何阻塞调用都**必须使用 `asyncio.to_thread`** 包装。
5.  **核心概念的正确使用:** 贡献的代码必须正确使用 `business_id` 和 `context` 等核心概念。关于它们的使用场景和最佳实践，请参阅 [**高级用法指南**](./docs/guides/02_advanced_usage.md)。
6.  **性能优先的数据库设计:** 所有数据库相关的代码和 Schema 变更，都必须遵循性能最佳实践。详细规范请参阅 [**数据模型与数据库设计**](./docs/architecture/02_data_model.md)。

---


<!-- English -->
### **Engine Development Specifications**

<!-- 简体中文 -->
### **引擎开发规范**

---


<!-- English -->
All newly contributed translation engines must adhere to a strict development model to ensure compatibility and maintainability with the core system.

<!-- 简体中文 -->
所有新贡献的翻译引擎都必须遵循严格的开发模式，以确保与核心系统的兼容性和可维护性。

---


<!-- English -->
- **Core Requirement**: The new engine must inherit from `BaseTranslationEngine` and implement the `_atranslate_one` asynchronous method. All batch processing and concurrency logic are handled by the base class.
- **Detailed Guide**: Before starting development, be sure to read and follow every step in the [**New Engine Development Guide**](./docs/contributing/developing_engines.md).

<!-- 简体中文 -->
- **核心要求**: 新引擎必须继承 `BaseTranslationEngine` 并实现 `_atranslate_one` 异步方法。所有批处理和并发逻辑均由基类处理。
- **详细指南**: 在开始开发前，请务必完整阅读并遵循 [**新引擎开发指南**](./docs/contributing/developing_engines.md) 中的每一个步骤。

---


<!-- English -->
### **Test**

<!-- 简体中文 -->
### **测试**

---


<!-- English -->
1.  **Comprehensive Testing:** All new features or bug fixes must be accompanied by corresponding unit tests or integration tests. We encourage the use of test-driven development (TDD) practices.
2.  **Test Coverage:** The target coverage for core business logic is > 90%.
3.  **Mocking External Dependencies:** All external services (such as API calls) must be mocked in tests to ensure stability and speed. It is recommended to use `unittest.mock.patch`.

4.  **Testing Code Guidelines**:
    -   **Separation of Concerns:** The responsibility of test code is to **validate** the functionality of core code. It **should not** contain any logic for "fixing" or "working around" design flaws in the core library. If tests are difficult to write, it usually indicates that the core code needs refactoring.
    -   **Fixture Design**:
        -   **Simplified Fixtures:** `pytest` fixtures (especially `test_config`) should be as **simple** as possible, only responsible for providing the most basic configurations that align with typical user scenarios.
        -   **Trust Core Logic:** Do not manually construct complex internal states for testing. Trust the initialization logic of the component being tested (such as `Coordinator`) to correctly assemble its dependencies.
    -   **Tests Should Focus on Behavior, Not Implementation Details:** Our tests should verify "when I call `coordinator.switch_engine('openai')`, does it work correctly," rather than verifying "is `config.engine_configs.openai` created correctly." The latter is an implementation detail of `Coordinator`.
    -   **Handling Conflicts Between Dynamic Models and MyPy:**
        - **Scenario:** Some Pydantic models in `Trans-Hub` (such as `EngineConfigs`) are designed to be dynamic (`extra="allow"`). This may cause `mypy` to complain during static analysis about fields or types passed to these models that it cannot see in static definitions.
        - **Solution:** In this specific case, to maintain the purity of core code, we allow the use of `# type: ignore` in **test code** to suppress `mypy`'s `[arg-type]` or `[call-arg]` errors. This is the best practice to address the limitations of static analyzers without polluting the core library implementation.
        ```python
        # Good practice: use type: ignore in test code to resolve dynamic model issues
        engine_configs_dict = {"dynamic_field": SomeConfig()}
        
        config = TransHubConfig(
            engine_configs=engine_configs_dict,  # type: ignore[arg-type]
        )
        ```

<!-- 简体中文 -->
1.  **全面测试:** 所有新功能或 Bug 修复都必须附带相应的单元测试或集成测试。我们鼓励使用测试驱动开发（TDD）的模式。
2.  **测试覆盖率:** 核心业务逻辑的目标覆盖率 > 90%。
3.  **模拟外部依赖:** 测试中必须模拟所有外部服务（如 API 调用），以确保测试的稳定性和速度。推荐使用 `unittest.mock.patch`。

4.  **测试代码编写准则**:
    -   **职责分离**: 测试代码的职责是**验证**核心代码的功能。它**不应该**包含任何用于“修复”或“变通”核心库设计缺陷的逻辑。如果测试很难写，通常意味着核心代码需要重构。
    -   **Fixture 设计**:
        -   **简化 Fixture**: `pytest` 的 fixture (特别是 `test_config`) 应该尽可能地**简单**，只负责提供最基本的、符合用户常规使用场景的配置。
        -   **信赖核心逻辑**: 不要为了测试而去手动构建复杂的内部状态。应该信赖被测试组件（如 `Coordinator`）的初始化逻辑来正确地组装其依赖。
    -   **测试应关注行为，而非实现细节**: 我们的测试应该验证“当我调用 `coordinator.switch_engine('openai')` 时，它是否能正常工作”，而不是去验证“`config.engine_configs.openai` 是否被正确创建”。后者是 `Coordinator` 的实现细节。
    -   **处理动态模型与 MyPy 的冲突**:
        - **情景**: `Trans-Hub` 的某些 Pydantic 模型（如 `EngineConfigs`）被设计为动态的 (`extra="allow"`)。这可能导致 `mypy` 在静态分析时，抱怨向这些模型传递了它在静态定义中看不到的字段或类型。
        - **解决方案**: 在这种特定情况下，为了保持核心代码的纯粹性，我们允许在**测试代码**中使用 `# type: ignore` 来抑制 `mypy` 的 `[arg-type]` 或 `[call-arg]` 错误。这是在不污染核心库实现的情况下，解决静态分析器局限性的最佳实践。
        ```python
        # 好的实践：在测试代码中，用 type: ignore 解决动态模型问题
        engine_configs_dict = {"dynamic_field": SomeConfig()}
        
        config = TransHubConfig(
            engine_configs=engine_configs_dict,  # type: ignore[arg-type]
        )
        ```

---


<!-- English -->
### **Other Key Agreements**

<!-- 简体中文 -->
### **其他关键约定**

---


<!-- English -->
1.  **Exception Handling:** Capture specific exception types and define custom exceptions if necessary.  
2.  **Security:** Use `SecretStr` to handle sensitive information and regularly check for dependency vulnerabilities.  
3.  **Database Evolution:** Any schema changes **must be implemented through new migration scripts**.  
4.  **Documentation:** In addition to in-code documentation, maintain the `README.md` and `docs/` directory.

<!-- 简体中文 -->
1.  **异常处理:** 捕获具体的异常类型，必要时定义自定义异常。
2.  **安全性:** 使用 `SecretStr` 处理敏感信息，定期检查依赖漏洞。
3.  **数据库演进:** 任何 Schema 变更都**必须通过新的迁移脚本**实现。
4.  **文档:** 除了代码内文档，还需维护 `README.md` 和 `docs/` 目录。

---


<!-- English -->
Thank you again for your contribution! We look forward to building `Trans-Hub` together with you.

<!-- 简体中文 -->
再次感谢您的贡献！我们期待与您共建 `Trans-Hub`。
