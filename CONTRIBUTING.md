# 为 `Trans-Hub` 做出贡献

我们非常欢迎并感谢您有兴趣为 `Trans-Hub` 做出贡献！无论是报告 bug、提交功能请求，还是直接贡献代码，您的每一份努力都对我们至关重要。❤️

---

## **目录**

- [行为准则](#1-行为准则)
- [如何贡献](#2-如何贡献)
- [代码库结构概览](#3-代码库结构概览)
- [环境设置](#4-环境设置)
- [日常开发工作流](#5-日常开发工作流)
- [提交 Pull Request](#6-提交-pull-request)
- [发布流程 (核心维护者指南)](#7-发布流程-核心维护者指南)

---

## **1. 行为准则**

为了营造一个开放、友好的社区环境，我们希望所有参与者都能遵守我们的 [**行为准则 (Code of Conduct)**](./CODE_OF_CONDUCT.md)。

## **2. 如何贡献**

我们欢迎任何形式的贡献，包括但不限于：
- **报告 Bug** 或 **提交功能建议** (通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues))。
- **完善文档**：发现拼写错误或不清晰之处？提交一个 PR 来改进它！
- **编写代码**：修复 Bug 或实现新功能。

## **3. 代码库结构概览**

为了帮助您快速熟悉项目，以下是核心目录及其中关键脚本的职责说明：

- **`trans_hub/`**: **核心库代码**。项目的所有运行时逻辑都在这里。

- **`tests/`**: **自动化测试**。
  - **`test_main.py`**: 这是项目的**核心功能测试套件**。它使用 `pytest` 来自动化地验证所有主要功能是否按预期工作。**CI/CD 流水线会自动运行此文件。**
    ```bash
    # 运行完整的测试套件
    poetry run pytest
    ```
  - **`diag/check_env.py`**: 一个独立的**诊断脚本**，专门用于快速验证 `.env` 文件中的配置是否能被正确加载。当您遇到与 API Key 相关的配置问题时，它非常有用。
    ```bash
    # 运行环境检查脚本
    poetry run python tests/diag/check_env.py
    ```

- **`docs/`**: **官方文档**。所有面向用户的指南、API参考和架构文档都存放在这里。

- **`examples/`**: **“活”的示例代码**。
  - **`demo_complex_workflow.py`**: 这是一个**端到端的、功能完善的演示**。它旨在向人类用户直观地、可运行地展示如何在一个复杂的场景中使用 `Trans-Hub` 的各项核心功能。
    ```bash
    # 运行复杂工作流演示
    poetry run python examples/demo_complex_workflow.py
    ```

- **`tools/`**: **开发者工具**。
  - **`inspect_db.py`**: 一个专业的**数据库检查命令行工具**。它能连接到任何 `Trans-Hub` 数据库文件，并以一种易于理解的方式将其内容和解读打印出来，是调试持久化问题的利器。
    ```bash
    # 检查示例数据库的内容
    poetry run python tools/inspect_db.py examples/complex_demo.db
    ```

## **4. 环境设置**

1.  **克隆仓库**: `git clone https://github.com/SakenW/trans-hub.git && cd trans-hub`
2.  **安装 Poetry**: 请确保您已安装 [Poetry](https://python-poetry.org/)。
3.  **安装所有依赖**: `poetry install --with dev`
4.  **运行测试套件**: 在开始编码前，请运行 `poetry run pytest` 确保本地环境正常。

## **5. 日常开发工作流**

在每次提交代码前，请执行以下三步，以确保代码质量：

1.  **格式化**: `poetry run ruff format .`
2.  **检查与修复**: `poetry run ruff check --fix .`
3.  **类型检查**: `poetry run mypy .`

## **6. 提交 Pull Request**

1.  完成开发和测试后，创建一个 Pull Request (PR)，目标分支为 `main`。
2.  在 PR 的描述中，请清晰地说明您解决了什么问题或实现了什么功能。
3.  请确保您的 PR 通过了我们 CI 流水线的所有自动化检查。
4.  项目维护者会尽快审查您的代码。

---

## **7. 发布流程 (核心维护者指南)**

这是一个为项目核心维护者准备的、严格的版本发布标准作业流程 (SOP)。

### **阶段一：本地准备**
1.  更新 `pyproject.toml` 中的 `version` 字段。
2.  在 `CHANGELOG.md` 顶部为新版本添加详尽的变更记录。
3.  确保所有相关文档都已同步。
4.  运行 `poetry lock` 更新锁文件。
5.  **最终本地验证**: `poetry run pytest && poetry run mypy . && poetry run ruff check .`
6.  构建发布包: `poetry build`

### **阶段二：技术发布与验证**
1.  配置 PyPI API 令牌: `poetry config pypi-token.pypi <你的令牌>`
2.  执行发布: `poetry publish`
3.  **立即在全新环境中测试安装**:
    ```bash
    # 在项目目录之外
    python -m venv .venv && source .venv/bin/activate
    pip install "trans-hub==<新版本号>"
    # 运行一个简单的测试脚本，确保核心功能正常
    deactivate
    ```
    > 🚨 如果此步骤失败，立即去 PyPI **废弃 (Yank)** 该版本，修复问题，然后从阶段一重新开始。

### **阶段三：官方发布定稿**
**只有在阶段二成功通过后**，才能进入此阶段。
1.  提交所有发布相关文件: `git commit -m "chore(release): release v<新版本号>"`
2.  创建 Git 标签: `git tag v<新版本号>`
3.  推送所有内容: `git push && git push --tags`

### **阶段四：社区沟通**
1.  在 GitHub 基于新标签创建 Release，并将 `CHANGELOG.md` 的内容作为说明。

---

再次感谢您的贡献！我们期待与您共建 `Trans-Hub`。