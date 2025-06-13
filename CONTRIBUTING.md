# **为 `Trans-Hub` 做出贡献**

我们非常欢迎并感谢您有兴趣为 `Trans-Hub` 做出贡献！无论是报告 bug、提交功能请求，还是直接贡献代码，您的每一份努力都对我们至关重要。❤️

---

## **目录**
- [如何贡献](#如何贡献)
- [行为准则](#行为准-则)
- [环境设置](#环境设置)
- [开发与测试脚本指南](#开发与测试脚本指南)
  - [`demo_complex_workflow.py` - 复杂工作流演示脚本](#demo_complex_workflowpy---复杂工作流演示脚本)
  - [`run_coordinator_test.py` - 端到端功能测试脚本](#run_coordinator_testpy---端到端功能测试脚本)
  - [`tools/inspect_db.py` - 数据库检查工具](#toolsinspect_dbpy---数据库检查工具)
- [开发工作流](#开发工作流)
  - [分支管理](#分支管理)
  - [代码风格与质量检查](#代码风格与质量检查)
  - [提交信息规范](#提交信息规范)
- [提交 Pull Request](#提交-pull-request)
- [报告 Bug 或提交功能建议](#报告-bug-或提交功能建议)

---

## **如何贡献**

我们欢迎任何形式的贡献，包括但不限于：
*   **报告 Bug**: 如果您在使用中发现了问题，请通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 告诉我们。
*   **提交功能建议**: 如果您有绝妙的想法，欢迎通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 分享。
*   **完善文档**: 发现文档中的拼写错误或不清晰之处？提交一个 PR 来改进它！
*   **编写代码**: 修复 Bug 或实现新功能。这是我们最欢迎的贡献方式！

## **行为准则**

为了营造一个开放、友好的社区环境，我们希望所有参与者都能遵守我们的 [**行为准则 (Code of Conduct)**](./CODE_OF_CONDUCT.md)。请在参与贡献前花时间阅读它。

## **环境设置**

为了能够进行开发和测试，您需要先设置好本地开发环境。

1.  **克隆仓库**:
    ```bash
    git clone https://github.com/SakenW/trans-hub.git
    cd trans-hub
    ```

2.  **安装 Poetry**:
    `Trans-Hub` 使用 [Poetry](https://python-poetry.org/) 进行依赖管理。请确保您已经安装了它。

3.  **安装所有依赖**:
    运行以下命令来创建一个虚拟环境，并安装所有核心、开发和可选依赖。
    ```bash
    poetry install --with dev
    ```

4.  **运行测试套件**:
    在进行任何代码修改之前，请先运行完整的测试套件，以确保您的本地环境是正常的。
    ```bash
    poetry run python run_coordinator_test.py
    ```
    如果所有测试都通过了，您就可以开始编码了！

## **开发与测试脚本指南**

在 `Trans-Hub` 项目的根目录下，有几个非核心库的 Python 脚本，它们在开发、测试和演示中扮演着重要角色。

### `demo_complex_workflow.py` - 复杂工作流演示脚本

*   **用途**: 这个脚本是 `Trans-Hub` 的**“活文档”和“教学演示”**。它旨在向人类用户（开发者、新贡献者）直观地展示 `Trans-Hub` 的各项核心功能（如上下文翻译、缓存、垃圾回收等）是如何协同工作的。
*   **特点**:
    *   **行为导向**: 它的主要输出是详细的、人类可读的日志流，让您可以清晰地观察到每个阶段发生了什么。
    *   **沙盒环境**: 每次运行时，它都会删除并重新创建数据库，确保演示环境的纯净和结果的可预测性。
    *   **快速实验**: 这是您尝试新想法、复现特定场景或快速验证某个小改动的最佳平台。
*   **关于垃圾回收 (GC) 的说明**:
    *   由于 `Trans-Hub v1.1.0` 的 GC 逻辑已优化为基于**日期**进行比较，此脚本在单次运行时，**你将观察到 GC 不会清理任何记录**。
    *   这是**预期行为**，因为所有 `business_id` 的 `last_seen_at` 时间戳都是“今天”，而 `gc_retention_days=0` 的设置意味着只清理“今天之前”的记录。
    *   这个脚本仍然完美地展示了 `request` 和 `process_pending_translations` 的完整流程。要查看 GC 清理记录的实际测试，请参考 `run_coordinator_test.py`，其中通过手动修改时间戳来模拟时间的流逝。
*   **如何运行**:
    ```bash
    # 从项目根目录运行
    poetry run python demo_complex_workflow.py
    ```

### `run_coordinator_test.py` - 端到端功能测试脚本

*   **用途**: 这个脚本是项目的**“质量保证守门员”**。它通过程序化的方式，自动化地验证 `Trans-Hub` 的核心功能是否按预期工作。
*   **特点**:
    *   **验证导向**: 它的核心是 `assert` 语句。如果任何一个功能不符合预期，`assert` 就会失败，程序会立即报错并退出。
    *   **CI/CD 核心**: 这个脚本是 GitHub Actions 等持续集成流程中必须运行的一环，确保了每次代码提交都不会破坏现有功能。
    *   **开发者必备**: 在提交任何代码修改之前，您都应该运行此脚本，以确保您的更改没有引入新的问题。
*   **如何运行**:
    ```bash
    # 从项目根目录运行
    poetry run python run_coordinator_test.py
    ```

### `tools/inspect_db.py` - 数据库检查工具

*   **用途**: 这是一个轻量级的**辅助调试工具**。当您运行完演示或测试脚本后，可以用它来连接到生成的 SQLite 数据库，并以一种格式化、带解读的方式打印出所有翻译记录。
*   **特点**:
    *   **直观的数据库快照**: 它能帮助您深入理解 `th_content`, `th_translations`, `th_sources` 这三张核心表是如何关联和存储数据的。
    *   **路径自适应**: 脚本会自动向上查找项目根目录（通过 `pyproject.toml` 文件识别），因此无论您在哪个目录下运行它，它都能正确找到位于根目录的数据库文件。
*   **如何运行**:
    **前提**: 必须先运行 `demo_complex_workflow.py` 来生成 `my_complex_trans_hub_demo.db` 文件。
    ```bash
    # 从项目根目录运行
    poetry run python tools/inspect_db.py
    ```

## **开发工作流**

为了保持代码库的整洁和一致性，请遵循以下工作流程。

### **分支管理**

1.  **从 `main` 分支创建**: 所有的功能开发或 Bug 修复都应该从最新的 `main` 分支创建新的分支。
2.  **命名约定**: 我们推荐使用以下格式为您的分支命名：
    *   **新功能**: `feat/a-brief-description` (例如: `feat/add-deepl-engine`)
    *   **Bug修复**: `fix/issue-number-or-description` (例如: `fix/issue-123-gc-logic`)
    *   **文档**: `docs/update-readme`
    *   **重构**: `refactor/improve-persistence-layer`

### **代码风格与质量检查**

我们使用 `ruff`, `black`, `isort` 和 `mypy` 来确保代码质量和类型安全。在提交代码前，请务必运行以下命令，并确保所有检查都通过。

*   **格式化与检查 (推荐)**: `ruff` 提供了格式化和代码检查的一体化方案。
    ```bash
    # 自动修复所有可修复的问题，并格式化代码
    poetry run ruff check . --fix
    poetry run ruff format .
    ```
*   **类型检查**: 我们使用 `mypy` 进行严格的静态类型检查。
    ```bash
    poetry run mypy .
    ```

> 💡 **提示**: 我们已经在 `.vscode/settings.json` 中配置了在保存时自动运行 `ruff` 进行格式化和检查。如果您使用 VS Code，这将极大地提升您的开发效率。

### **提交信息规范**

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。这有助于自动化生成更新日志（CHANGELOG）并保持提交历史的清晰。

**格式**: `<type>(<scope>): <subject>`

*   **`type`**: `feat` (新功能), `fix` (Bug修复), `docs` (文档), `style` (代码风格), `refactor` (重构), `test` (测试), `chore` (构建或工具)
*   **`scope`** (可选): 本次修改影响的范围 (例如: `engine`, `coordinator`, `persistence`)
*   **`subject`**: 简明扼要的描述。

**示例**:
*   `feat(engine): Add DeepL translation engine`
*   `fix(persistence): Correct query logic in garbage collection`
*   `docs: Update README with new installation instructions`
*   `refactor(coordinator): Simplify business_id retrieval logic`
*   `chore: Update poetry.lock to match dependencies`

## **提交 Pull Request**

1.  当您完成开发和测试后，将您的分支推送到您自己的 Fork 仓库。
2.  在 `Trans-Hub` 的 GitHub 页面上，创建一个 Pull Request (PR)，目标分支为 `main`。
3.  在 PR 的描述中，请清晰地说明：
    *   **您解决了什么问题或实现了什么功能？** (可以链接到相关的 Issue)
    *   **您是如何实现的？** (简要描述您的技术方案)
    *   **您是如何测试的？** (说明您新增或修改了哪些测试)
4.  请确保您的 PR 通过了我们 CI/CD 流水线的所有自动化检查。
5.  项目维护者会尽快审查您的代码，并可能提出修改建议。请保持沟通！

## **报告 Bug 或提交功能建议**

我们使用 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 来追踪所有的 Bug 和功能请求。

在提交 Issue 之前，请先搜索一下是否已经存在类似的 Issue。

*   **对于 Bug 报告**: 请提供尽可能详细的信息，包括：您使用的 `Trans-Hub` 版本、Python 版本、操作系统、以及可以复现问题的最小代码片段和完整的错误堆栈。
*   **对于功能建议**: 请清晰地描述您想要的功能，以及它能解决什么样的问题。

再次感谢您的贡献！我们期待与您共建 `Trans-Hub`。