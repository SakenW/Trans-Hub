
We warmly welcome and thank you for your interest in contributing to `Trans-Hub`! Whether it's reporting bugs, submitting feature requests, or directly contributing code, every effort you make is vital to us. ❤️

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **目录**

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发规范总则](#开发规范总则)
- [代码库结构概览](#代码库结构概览)
- [环境设置](#环境设置)
- [提交前的本地检查清单](#提交前的本地检查清单)
- [提交 Pull Request](#提交-pull-request)
- [附录：详细开发规范](#附录详细开发规范)
  - [语言与沟通](#语言与沟通)
  - [代码风格与质量](#代码风格与质量)
  - [架构与设计](#架构与设计)
  - [引擎开发规范](#引擎开发规范)
  - [测试](#测试)
  - [其他关键约定](#其他关键约定)
- [发布流程](#发布流程)

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **Code of Conduct**

To create an open and friendly community environment, we hope that all participants will adhere to our [**Code of Conduct**](./CODE_OF_CONDUCT.md).

## **How to Contribute**

We welcome any form of contribution, including but not limited to:

- **Report a Bug** or **Submit a Feature Suggestion** (via [GitHub Issues](https://github.com/SakenW/trans-hub/issues)).
- **Improve Documentation**: Found a typo or something unclear? Submit a PR to improve it!
- **Write Code**: Fix bugs or implement new features.

## **General Principles of Development Specifications**

Before starting any coding work, please be sure to carefully read the [Appendix: Detailed Development Specifications](#Appendix-Detailed-Development-Specifications) at the end of this document.

Trans-Hub" is a project with strict requirements for code quality, architectural clarity, and maintainability. All contributed code must strictly adhere to these standards. This ensures the project can develop healthily in the long term.

## **Overview of Code Repository Structure**

To help you quickly familiarize yourself with the project, here are the core directories and the responsibilities of the key scripts within them:

- **`trans_hub/`**: **Core library code**. All runtime logic of the project is here.

- **`tests/`**: **Automated Testing**.

  - This directory contains all the test cases for the project (using `pytest`). The CI/CD pipeline will automatically run all tests in this directory.
    ```bash
    # Run the complete test suite
    poetry run pytest
    ```
  - **`tests/diag/`**: Contains some standalone **diagnostic scripts**.
    - `check_env.py`: Specifically designed for quickly validating the configuration of the `.env` file. It is very useful when you encounter configuration issues related to the API Key.
      ```bash
      # Run the environment check script
      poetry run python tests/diag/check_env.py
      ```

- **`docs/`**: **Official Documentation**. All user-facing guides, API references, and architectural documentation are stored here. Please read the [**Documentation Index (INDEX.md)**](./docs/INDEX.md) first to understand its structure.

- **`examples/`**: **Example code for "living".**

  - **`translate_strings_file.py`**: This is a **fully functional end-to-end demonstration**. It is designed to intuitively and operationally show human users how to use the core features of `Trans-Hub` in a complex scenario.
    ```bash
    # Run complex workflow demonstration
    poetry run python examples/translate_strings_file.py
    ```

- **`tools/`**: **Developer Tools**.
  - **`inspect_db.py`**: A specialized **database inspection command-line tool**. It can connect to any `Trans-Hub` database file and print its contents and interpretations in an easy-to-understand manner, making it a powerful tool for debugging persistence issues.
    ```bash
    # Check the contents of the example database
    poetry run python tools/inspect_db.py examples/strings_translator_demo_dynamic.db
    ```

## **Environment Setup**

1.  **Clone the repository**: `git clone https://github.com/SakenW/trans-hub.git && cd trans-hub`
2.  **Install Poetry**: Please ensure you have installed [Poetry](https://python-poetry.org/).
3.  **Install all dependencies**: `poetry install --with dev --with openai`
4.  **Configure environment variables**: Create your local `.env` file based on the `.env.example` template and fill in the necessary API keys to run the full test suite.
    ```bash
    cp .env.example .env
    ```
5.  **Run the test suite**: Before you start coding, please run `poetry run pytest` to ensure the local environment is working properly.

## **Local Checklist Before Submission**

Before you execute `git commit`, please make sure to run the following three commands locally to ensure your code meets the project's quality standards. This can prevent your Pull Request from being rejected due to CI/CD check failures after submission.

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

> **Tip**: Running these commands frequently is a good habit.

## **Submit Pull Request**

1. After completing development and testing, create a Pull Request (PR) with the target branch as `main`.  
2. In the PR description, please clearly state what issue you have resolved or what feature you have implemented. We recommend using the [PR template](./.github/pull_request_template.md) provided by the project.  
3. Please ensure that your PR passes all automated checks in our CI pipeline.  
4. Project maintainers will review your code as soon as possible.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **附录：详细开发规范**

本节是所有贡献者必须遵守的详细技术规范。

### **语言与沟通**

1.  **代码内语言:**
    - **注释、文档字符串 (Docstrings)、日志信息、用户可见字符串:** **必须全部使用中文**。
    - **变量/函数/类名等代码标识符:** **必须使用英文**，并遵循 PEP 8 命名约定。
2.  **沟通工具语言:**
    - **所有对话:** **默认使用中文**。
    - **AI Prompt:** 可以使用英文。

### **代码风格与质量**

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

### **架构与设计**

1.  **单一职责原则 (SRP):** 每个模块、类、函数只做一件事。
2.  **依赖倒置原则 (DIP):** 核心逻辑依赖抽象（`Protocol`），而非具体实现。
3.  **配置分离:** 严禁硬编码。所有配置项必须在 `config.py` 中定义，并通过 `pydantic-settings` 加载。
4.  **纯异步优先:** 核心工作流必须异步。任何阻塞调用都**必须使用 `asyncio.to_thread`** 包装。
5.  **核心概念的正确使用:** 贡献的代码必须正确使用 `business_id` 和 `context` 等核心概念。关于它们的使用场景和最佳实践，请参阅 [**高级用法指南**](./docs/guides/02_advanced_usage.md)。
6.  **性能优先的数据库设计:** 所有数据库相关的代码和 Schema 变更，都必须遵循性能最佳实践。详细规范请参阅 [**数据模型与数据库设计**](./docs/architecture/02_data_model.md)。

### **引擎开发规范**

所有新贡献的翻译引擎都必须遵循严格的开发模式，以确保与核心系统的兼容性和可维护性。

- **核心要求**: 新引擎必须继承 `BaseTranslationEngine` 并实现 `_atranslate_one` 异步方法。所有批处理和并发逻辑均由基类处理。
- **详细指南**: 在开始开发前，请务必完整阅读并遵循 [**新引擎开发指南**](./docs/contributing/developing_engines.md) 中的每一个步骤。

### **测试**

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

### **其他关键约定**

1.  **异常处理:** 捕获具体的异常类型，必要时定义自定义异常。
2.  **安全性:** 使用 `SecretStr` 处理敏感信息，定期检查依赖漏洞。
3.  **数据库演进:** 任何 Schema 变更都**必须通过新的迁移脚本**实现。
4.  **文档:** 除了代码内文档，还需维护 `README.md` 和 `docs/` 目录。

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **Release Process**

> 🚨 **Note**: This section is only applicable to the core maintainers of the project.

This project follows a strict and detailed standard operating procedure (SOP) for version releases to ensure the quality and reliability of each version.

👉 **[Click here to view the complete release standard operating procedure (SOP)](./RELEASE_SOP.md)**

It seems there is no text provided for translation. Please provide the text you would like to have translated.

Thank you again for your contribution! We look forward to building `Trans-Hub` together with you.
