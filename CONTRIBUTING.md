# 为 `Trans-Hub` 做出贡献

首先，非常感谢您愿意花时间为 `Trans-Hub` 做出贡献！正是因为有像您一样热情的开发者，开源社区才能不断壮大。❤️

本指南旨在为您提供清晰的指引，让您的贡献过程尽可能顺畅。

## 目录
- [如何贡献](#如何贡献)
- [行为准则](#行为准则)
- [环境设置](#环境设置)
- [开发工作流](#开发工作流)
  - [分支管理](#分支管理)
  - [代码风格](#代码风格)
  - [提交信息规范](#提交信息规范)
- [提交 Pull Request](#提交-pull-request)
- [报告 Bug 或提交功能建议](#报告-bug-或提交功能建议)

---

## 如何贡献

我们欢迎任何形式的贡献，包括但不限于：
*   **报告 Bug**: 如果您在使用中发现了问题，请通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 告诉我们。
*   **提交功能建议**: 如果您有绝妙的想法，欢迎通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 分享。
*   **完善文档**: 发现文档中的拼写错误或不清晰之处？提交一个 PR 来改进它！
*   **编写代码**: 修复 Bug 或实现新功能。这是我们最欢迎的贡献方式！

## 行为准则

为了营造一个开放、友好的社区环境，我们希望所有参与者都能遵守我们的 [行为准则 (Code of Conduct)](./CODE_OF_CONDUCT.md)。请在参与贡献前花时间阅读它。
*(注：您需要创建一个 `CODE_OF_CONDUCT.md` 文件，通常可以直接采用社区模板，例如 [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct.md))*

## 环境设置

为了能够进行开发和测试，您需要先设置好本地开发环境。

1.  **克隆仓库**:
    ```bash
    git clone https://github.com/SakenW/trans-hub.git
    cd trans-hub
    ```

2.  **安装 Poetry**:
    `Trans-Hub` 使用 [Poetry](https://python-poetry.org/) 进行依赖管理。请确保您已经安装了它。

3.  **安装所有依赖**:
    运行以下命令来创建一个虚拟环境，并安装所有核心、开发和可选依赖。这是进行完整测试所必需的。
    ```bash
    poetry install --with dev --all-extras
    ```

4.  **运行测试套件**:
    在进行任何代码修改之前，请先运行完整的测试套件，以确保您的本地环境是正常的。
    ```bash
    poetry run python run_coordinator_test.py
    ```
    如果所有测试都通过了，您就可以开始编码了！

## 开发工作流

为了保持代码库的整洁和一致性，请遵循以下工作流程。

### 分支管理

1.  **从 `main` 分支创建**: 所有的功能开发或 Bug 修复都应该从最新的 `main` 分支创建新的分支。
2.  **命名约定**: 我们推荐使用以下格式为您的分支命名：
    *   **新功能**: `feat/a-brief-description` (例如: `feat/add-deepl-engine`)
    *   **Bug修复**: `fix/issue-number-or-description` (例如: `fix/issue-123-gc-logic`)
    *   **文档**: `docs/update-readme`

### 代码风格

*   **格式化**: 我们使用 `black` 进行代码格式化，使用 `isort` 进行 import 排序。在提交代码前，请运行：
    ```bash
    poetry run black .
    poetry run isort .
    ```
*   **Linter**: 我们使用 `ruff` 进行代码质量检查。请确保您的代码没有 `ruff` 警告：
    ```bash
    poetry run ruff check .
    ```
*   **类型检查**: 我们使用 `mypy` 进行静态类型检查。请确保您的代码能通过类型检查：
    ```bash
    poetry run mypy .
    ```

> 💡 **提示**: 我们已经在 `.vscode/settings.json` 中配置了在保存时自动格式化和检查。如果您使用 VS Code，这将非常方便。

### 提交信息规范

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。这有助于自动化生成更新日志（CHANGELOG）并保持提交历史的清晰。

**格式**: `<type>(<scope>): <subject>`

*   **`type`**: `feat` (新功能), `fix` (Bug修复), `docs` (文档), `style` (代码风格), `refactor` (重构), `test` (测试), `chore` (构建或工具)
*   **`scope`** (可选): 本次修改影响的范围 (例如: `engine`, `coordinator`)
*   **`subject`**: 简明扼要的描述。

**示例**:
*   `feat(engine): Add DeepL translation engine`
*   `fix(persistence): Correct query logic in garbage collection`
*   `docs: Update README with new installation instructions`

## 提交 Pull Request

1.  当您完成开发和测试后，将您的分支推送到您自己的 Fork 仓库。
2.  在 `Trans-Hub` 的 GitHub 页面上，创建一个 Pull Request (PR)，目标分支为 `main`。
3.  在 PR 的描述中，请清晰地说明：
    *   **您解决了什么问题或实现了什么功能？** (可以链接到相关的 Issue)
    *   **您是如何实现的？** (简要描述您的技术方案)
    *   **您是如何测试的？** (说明您新增或修改了哪些测试)
4.  请确保您的 PR 通过了我们 CI/CD 流水线的所有自动化检查。
5.  项目维护者会尽快审查您的代码，并可能提出修改建议。请保持沟通！

## 报告 Bug 或提交功能建议

我们使用 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 来追踪所有的 Bug 和功能请求。

在提交 Issue 之前，请先搜索一下是否已经存在类似的 Issue。

*   **对于 Bug 报告**: 请提供尽可能详细的信息，包括：您使用的 `Trans-Hub` 版本、Python 版本、操作系统、以及可以复现问题的最小代码片段和完整的错误堆栈。
*   **对于功能建议**: 请清晰地描述您想要的功能，以及它能解决什么样的问题。

再次感谢您的贡献！