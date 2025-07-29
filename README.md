<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details open>
<summary><strong>English</strong></summary>

**English** | [简体中文](../../zh/root_files/README.md)

# **Trans-Hub: Your Asynchronous Localization Backend Engine** 🚀

[![Python CI/CD Pipeline](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/SakenW/trans-hub/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/SakenW/trans-hub)
[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python-designed embeddable asynchronous localization engine specifically for automating dynamic content translation.

Trans-Hub is an **asynchronous-first**, embeddable Python application with persistent storage, serving as an intelligent localization (i18n) backend engine. It aims to unify and simplify multilingual translation workflows, providing efficient, low-cost, and highly reliable translation capabilities for upper-layer applications through intelligent caching, pluggable translation engines, and robust error handling and policy control.

## **Core Features**

- **Pure Asynchronous Design**: Built on `asyncio`, perfectly integrates with modern Python web frameworks like FastAPI and Starlette.
- **Persistent Caching**: All translation requests and results are automatically stored in an SQLite database, avoiding duplicate translations and saving costs.
- **Plugin-based Translation Engine**:
  - **Dynamic Discovery**: Automatically discovers all engine plugins in the `engines/` directory.
  - **Out of the Box**: Built-in free engines based on `translators`.
  - **Easy Expansion**: Supports advanced engines like `OpenAI` and provides clear guidelines for easily adding your own engines.
- **Intelligent Configuration**: Uses `Pydantic` for type-safe configuration management and can automatically load from `.env` files.
- **Robust Workflow**:
  - **Background Processing**: Separation of `request` (registration) and `process` (handling) ensures quick API responses.
  - **Automatic Retry**: Built-in retry mechanism with exponential backoff to gracefully handle network fluctuations.
  - **Rate Limiting**: Configurable token bucket rate limiter to protect your API key.
- **Data Lifecycle Management**: Built-in garbage collection (GC) functionality to regularly clean up outdated data.

## **🚀 Quick Start**

We have provided several 'living document' examples to help you quickly understand the usage of `Trans-Hub`.

1.  **Basic Usage**: Learn how to complete your first translation task in 5 minutes.
    ```bash
    # For details, please check the comments in the file
    poetry run python examples/01_basic_usage.py
    ```

2.  **Real World Simulation**: Want to see how `Trans-Hub` performs in a high concurrency, multi-task environment? This ultimate demonstration will run content producers, background translation workers, and API query services simultaneously.
    ```bash
    # (You need to configure the OpenAI API key in the .env file first)
    poetry run python examples/02_real_world_simulation.py
    ```

For more specific use cases (such as translating `.strings` files), please browse the `examples/` directory directly.

## **📚 Document**

We have a comprehensive documentation library to help you gain a deeper understanding of all aspects of `Trans-Hub`.

👉 [Click here to start exploring our documentation](./docs/en/index.md)

## **Contribution**

We warmly welcome any form of contribution! Please read our **[Contribution Guidelines](./CONTRIBUTING.md)** to get started.

## **License**

This project uses the MIT License. See the [LICENSE.md](./LICENSE.md) file for details.

</details>

<details>
<summary><strong>简体中文</strong></summary>

**English** | [简体中文](../../zh/root_files/README.md)

# **Trans-Hub: Your Asynchronous Localization Backend Engine** 🚀

[![Python CI/CD Pipeline](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/SakenW/trans-hub/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/SakenW/trans-hub/graph/badge.svg?token=YOUR_CODECOV_TOKEN)](https://codecov.io/gh/SakenW/trans-hub)
[![PyPI version](https://badge.fury.io/py/trans-hub.svg)](https://badge.fury.io/py/trans-hub)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python-designed embeddable asynchronous localization engine specifically for automating dynamic content translation.

Trans-Hub is an **asynchronous-first**, embeddable Python application with persistent storage, serving as an intelligent localization (i18n) backend engine. It aims to unify and simplify multilingual translation workflows, providing efficient, low-cost, and highly reliable translation capabilities for upper-layer applications through intelligent caching, pluggable translation engines, and robust error handling and policy control.

## **Core Features**

- **Pure Asynchronous Design**: Built on `asyncio`, perfectly integrates with modern Python web frameworks like FastAPI and Starlette.
- **Persistent Caching**: All translation requests and results are automatically stored in an SQLite database, avoiding duplicate translations and saving costs.
- **Plugin-based Translation Engine**:
  - **Dynamic Discovery**: Automatically discovers all engine plugins in the `engines/` directory.
  - **Out of the Box**: Built-in free engines based on `translators`.
  - **Easy Expansion**: Supports advanced engines like `OpenAI` and provides clear guidelines for easily adding your own engines.
- **Intelligent Configuration**: Uses `Pydantic` for type-safe configuration management and can automatically load from `.env` files.
- **Robust Workflow**:
  - **Background Processing**: Separation of `request` (registration) and `process` (handling) ensures quick API responses.
  - **Automatic Retry**: Built-in retry mechanism with exponential backoff to gracefully handle network fluctuations.
  - **Rate Limiting**: Configurable token bucket rate limiter to protect your API key.
- **Data Lifecycle Management**: Built-in garbage collection (GC) functionality to regularly clean up outdated data.

## **🚀 Quick Start**

We have provided several 'living document' examples to help you quickly understand the usage of `Trans-Hub`.

1.  **Basic Usage**: Learn how to complete your first translation task in 5 minutes.
    ```bash
    # For details, please check the comments in the file
    poetry run python examples/01_basic_usage.py
    ```

2.  **Real World Simulation**: Want to see how `Trans-Hub` performs in a high concurrency, multi-task environment? This ultimate demonstration will run content producers, background translation workers, and API query services simultaneously.
    ```bash
    # (You need to configure the OpenAI API key in the .env file first)
    poetry run python examples/02_real_world_simulation.py
    ```

For more specific use cases (such as translating `.strings` files), please browse the `examples/` directory directly.

## **📚 Document**

We have a comprehensive documentation library to help you gain a deeper understanding of all aspects of `Trans-Hub`.

👉 [Click here to start exploring our documentation](./docs/en/index.md)

## **Contribution**

We warmly welcome any form of contribution! Please read our **[Contribution Guidelines](./CONTRIBUTING.md)** to get started.

## **License**

This project uses the MIT License. See the [LICENSE.md](./LICENSE.md) file for details.

</details>
