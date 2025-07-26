# Contribute to `Trans-Hub`

We warmly welcome and thank you for your interest in contributing to `Trans-Hub`! Whether it's reporting bugs, submitting feature requests, or directly contributing code, every effort you make is vital to us. ❤️

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **Table of Contents**

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [General Development Guidelines](#general-development-guidelines)
- [Codebase Structure Overview](#codebase-structure-overview)
- [Environment Setup](#environment-setup)
- [Local Checklist Before Submission](#local-checklist-before-submission)
- [Submit Pull Request](#submit-pull-request)
- [Appendix: Detailed Development Guidelines](#appendix-detailed-development-guidelines)
  - [Language and Communication](#language-and-communication)
  - [Code Style and Quality](#code-style-and-quality)
  - [Architecture and Design](#architecture-and-design)
  - [Engine Development Guidelines](#engine-development-guidelines)
  - [Testing](#testing)
  - [Other Key Agreements](#other-key-agreements)
- [Release Process](#release-process)

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

## **Appendix: Detailed Development Specifications**

This section is the detailed technical specifications that all contributors must adhere to.

### **Language and Communication**

1.  **Language in Code:**
    - **Comments, Docstrings, Log Information, User-visible Strings:** **Must all be in Chinese**.
    - **Variable/Function/Class Names and Other Code Identifiers:** **Must be in English** and follow PEP 8 naming conventions.
2.  **Language for Communication Tools:**
    - **All Conversations:** **Default to Chinese**.
    - **AI Prompt:** Can be in English.

### **Code Style and Quality**

1.  **Formatting:** Strictly follow `PEP 8`, use `ruff format`, with a line length limit of 88 characters.  
2.  **Static Checks:**  
    - **Linter:** Use `ruff`, configuration can be found in `pyproject.toml`.  
    - **Type Checking:** Use `mypy`, new code must have complete type annotations.  
3.  **Logging Standards:**  
    - **Must use `structlog`**, `print()` is prohibited for debugging.  
    - Fully utilize context binding features.  
    - Strictly adhere to log level semantics (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). `ERROR` and above levels must include `exc_info=True`.  
4.  **File Header Standards:**  
    - The first line of all `.py` files must be a comment identifying its full path, such as `# trans_hub/coordinator.py`.  
    - **Prohibited** to add informal status descriptions like `(modified version)` at the file header.  
    - Docstrings (`"""..."""`) **are only for** describing the current functionality of the module, **prohibited** from including any change history. The only place for change records is **Git commit messages** and **`CHANGELOG.md`**.  
5.  **Handling Linter Rule Exceptions (`# noqa`):**  
    -   **Principle:** We strive for 100% compliance with `ruff` rules. However, in rare cases, specific functionality or code readability may require local disabling of a rule.  
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

### **Architecture and Design**

1.  **Single Responsibility Principle (SRP):** Each module, class, or function should do one thing only.  
2.  **Dependency Inversion Principle (DIP):** Core logic depends on abstractions (`Protocol`), not on concrete implementations.  
3.  **Configuration Separation:** Hard coding is strictly prohibited. All configuration items must be defined in `config.py` and loaded via `pydantic-settings`.  
4.  **Pure Asynchronous First:** Core workflows must be asynchronous. Any blocking calls **must be wrapped with `asyncio.to_thread`**.  
5.  **Correct Use of Core Concepts:** Contributed code must correctly use core concepts such as `business_id` and `context`. For usage scenarios and best practices, please refer to the [**Advanced Usage Guide**](./docs/guides/02_advanced_usage.md).  
6.  **Performance-First Database Design:** All database-related code and schema changes must follow performance best practices. For detailed specifications, please refer to [**Data Model and Database Design**](./docs/architecture/02_data_model.md).

### **Engine Development Specifications**

All newly contributed translation engines must adhere to a strict development model to ensure compatibility and maintainability with the core system.

- **Core Requirement**: The new engine must inherit from `BaseTranslationEngine` and implement the `_atranslate_one` asynchronous method. All batch processing and concurrency logic are handled by the base class.
- **Detailed Guide**: Before starting development, please be sure to read and follow every step in the [**New Engine Development Guide**](./docs/contributing/developing_engines.md).

### **Test**

1.  **Comprehensive Testing:** All new features or bug fixes must be accompanied by corresponding unit tests or integration tests. We encourage the use of test-driven development (TDD) practices.  
2.  **Test Coverage:** The target coverage for core business logic is > 90%.  
3.  **Mocking External Dependencies:** All external services (such as API calls) must be mocked in tests to ensure stability and speed. It is recommended to use `unittest.mock.patch`.

4.  **Testing Code Writing Guidelines**:
    -   **Separation of Responsibilities**: The responsibility of the test code is to **verify** the functionality of the core code. It **should not** contain any logic for "fixing" or "working around" design flaws in the core library. If tests are difficult to write, it usually means the core code needs refactoring.
    -   **Fixture Design**:
        -   **Simplified Fixture**: The fixtures in `pytest` (especially `test_config`) should be as **simple** as possible, only responsible for providing the most basic configurations that align with typical user scenarios.
        -   **Trust Core Logic**: Do not manually construct complex internal states for testing. Trust the initialization logic of the component being tested (such as `Coordinator`) to correctly assemble its dependencies.
    -   **Tests Should Focus on Behavior, Not Implementation Details**: Our tests should verify "when I call `coordinator.switch_engine('openai')`, does it work correctly," rather than verifying "is `config.engine_configs.openai` created correctly." The latter is an implementation detail of `Coordinator`.
    -   **Handling Conflicts Between Dynamic Models and MyPy**:
        - **Scenario**: Some Pydantic models in `Trans-Hub` (such as `EngineConfigs`) are designed to be dynamic (`extra="allow"`). This may cause `mypy` to complain during static analysis about fields or types passed to these models that it cannot see in the static definitions.
        - **Solution**: In this specific case, to maintain the purity of the core code, we allow the use of `# type: ignore` in **test code** to suppress `mypy`'s `[arg-type]` or `[call-arg]` errors. This is the best practice to address the limitations of static analyzers without polluting the core library implementation.
        ```python
        # Good practice: Use type: ignore in test code to resolve dynamic model issues
        engine_configs_dict = {"dynamic_field": SomeConfig()}
        
        config = TransHubConfig(
            engine_configs=engine_configs_dict,  # type: ignore[arg-type]
        )
        ```

### **Other Key Agreements**

1.  **Exception Handling:** Capture specific types of exceptions and define custom exceptions if necessary.  
2.  **Security:** Use `SecretStr` to handle sensitive information and regularly check for dependency vulnerabilities.  
3.  **Database Evolution:** Any schema changes **must be implemented through new migration scripts**.  
4.  **Documentation:** In addition to in-code documentation, maintain the `README.md` and `docs/` directory.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

## **Release Process**

> 🚨 **Note**: This section is only applicable to the core maintainers of the project.

This project follows a strict and detailed standard operating procedure (SOP) for version releases to ensure the quality and reliability of each version.

👉 **[Click here to view the complete release standard operating procedure (SOP)](./RELEASE_SOP.md)**

It seems there is no text provided for translation. Please provide the text you would like to have translated.

Thank you again for your contribution! We look forward to building `Trans-Hub` together with you.
