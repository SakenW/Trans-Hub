# 为 `Trans-Hub` 做出贡献

我们非常欢迎并感谢您有兴趣为 `Trans-Hub` 做出贡献！无论是报告 bug、提交功能请求，还是直接贡献代码，您的每一份努力都对我们至关重要。❤️

---

## **目录**

- [如何贡献](#如何贡献)
- [行为准则](#行为准-则)
- [环境设置](#环境设置)
- [日常开发工作流](#日常开发工作流)
- [提交信息规范](#提交信息规范)
- [提交 Pull Request](#提交-pull-request)
- [发布流程 (核心维护者指南)](#发布流程-核心维护者指南)
- [报告 Bug 或提交功能建议](#报告-bug-或提交功能建议)
- [附录：开发与测试脚本指南](#附录开发与测试脚本指南)

---

## **如何贡献**

我们欢迎任何形式的贡献，包括但不限于：

- **报告 Bug**: 如果您在使用中发现了问题，请通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 告诉我们。
- **提交功能建议**: 如果您有绝妙的想法，欢迎通过 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 分享。
- **完善文档**: 发现文档中的拼写错误或不清晰之处？提交一个 PR 来改进它！
- **编写代码**: 修复 Bug 或实现新功能。这是我们最欢迎的贡献方式！

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
    在进行任何代码修改之前，请先运行与 CI 环境一致的完整测试套件，以确保您的本地环境是正常的。
    ```bash
    poetry run pytest --cov=trans_hub --cov-report=xml
    ```
    如果所有测试都通过了，您就可以开始编码了！

## **日常开发工作流**

为了保持代码库的整洁、高质量，并充分利用 `Ruff` 的强大功能，我们推荐以下简化的三步工作流。**这应在每次提交代码前执行**。

1.  **格式化代码**:
    此命令会根据 `pyproject.toml` 中的规则，自动格式化所有代码，包括优化 `import` 语句的顺序。

    ```bash
    poetry run ruff format .
    ```

2.  **检查并自动修复问题**:
    此命令会找出代码中的潜在问题（linter 规则），并自动修复大部分可安全修复的问题。

    ```bash
    poetry run ruff check --fix .
    ```

3.  **进行静态类型检查**:
    这是保证代码健壮性的关键一步，用于发现潜在的类型不匹配等运行时错误。
    ```bash
    poetry run mypy .
    ```

> 💡 **提示**: 我们已经在 `.vscode/settings.json` 中配置了在保存时自动运行 `ruff` 进行格式化和检查。如果您使用 VS Code，这将极大地提升您的开发效率。

## **提交信息规范**

我们遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。这有助于自动化生成更新日志（CHANGELOG）并保持提交历史的清晰。

**格式**: `<type>(<scope>): <subject>`

- **`type`**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- **`scope`** (可选): 本次修改影响的范围 (例如: `engine`, `coordinator`)
- **`subject`**: 简明扼要的描述。

**示例**:

- `feat(engine): Add DeepL translation engine`
- `fix(persistence): Correct query logic in garbage collection`
- `chore(release): Prepare for v1.1.1`

## **提交 Pull Request**

1.  当您完成开发和测试后，将您的分支推送到您自己的 Fork 仓库。
2.  在 `Trans-Hub` 的 GitHub 页面上，创建一个 Pull Request (PR)，目标分支为 `main`。
3.  在 PR 的描述中，请清晰地说明：
    - **您解决了什么问题或实现了什么功能？** (可以链接到相关的 Issue)
    - **您是如何实现的？** (简要描述您的技术方案)
    - **您是如何测试的？** (说明您新增或修改了哪些测试)
4.  请确保您的 PR 通过了我们 CI/CD 流水线的所有自动化检查。
5.  项目维护者会尽快审查您的代码，并可能提出修改建议。请保持沟通！

---

## **发布流程 (核心维护者指南)**

这是一个为项目核心维护者准备的、严格的版本发布标准作业流程 (SOP)。

我们将发布流程分为四个逻辑清晰、顺序严格的阶段。

### **阶段一：本地准备与构建 (Preparation & Build)**

此阶段的目标是准备好所有待发布的工件，并在本地进行最终验证。

1.  **更新版本文件**:
    - **`pyproject.toml`**: 更新 `version` 字段为新版本号（例如 `1.1.1`）。
    - **`CHANGELOG.md`**: 在文件顶部为新版本添加详尽的变更记录。
2.  **审查相关文档**:
    - 检查 `README.md` 和 `docs/` 目录，确保内容与新版本功能同步。
3.  **更新依赖锁文件**:
    - 运行 `poetry lock` 以同步 `poetry.lock` 文件。
4.  **最终本地验证 (CI 标准)**:
    - **运行带覆盖率报告的测试**:
      ```bash
      poetry run pytest --cov=trans_hub --cov-report=xml
      ```
    - **运行最终代码质量检查**:
      ```bash
      poetry run mypy .
      poetry run ruff check .
      ```
5.  **构建发布包**:
    - 运行 `poetry build`。此命令会创建 `dist/` 目录和里面的发布文件 (`.whl` 和 `.tar.gz`)。

**此刻状态**: 您的本地代码库已准备就绪，可以进行技术发布，但**尚未做任何 Git 提交**。

---

### **阶段二：技术发布与验证 (Publication & Verification)**

此阶段的目标是将软件包上传到 PyPI，并**立即验证**其可用性。这是在正式官宣前的最后一道质量关卡。

1.  **配置 PyPI 认证 (仅需一次)**:
    - 通过 PyPI 官网获取一个限定项目范围的 **API 令牌**。
    - 运行 `poetry config pypi-token.pypi <你的令牌>` 进行配置。
2.  **执行技术发布**:
    - 运行 `poetry publish`。Poetry 会上传 `dist/` 目录中的文件。
      ```bash
      poetry publish
      ```
3.  **立即进行线上验证 (关键步骤)**:

    - **检查 PyPI 页面**: 访问 [https://pypi.org/project/trans-hub/](https://pypi.org/project/trans-hub/)，确认新版本已显示，`README` 渲染正常。
    - **在全新环境中测试安装**: 这是最关键的验证。

      ```bash
      # 1. 创建一个全新的、干净的虚拟环境 (在项目目录之外)
      mkdir ~/temp-pypi-test && cd ~/temp-pypi-test
      python -m venv .venv
      source .venv/bin/activate

      # 2. 从 PyPI 安装刚刚发布的版本
      pip install "trans-hub==<新版本号>"

      # 3. 运行一个简单的测试脚本 (例如 README 中的 quick_start.py)
      #    以确保包的核心功能正常工作。
      ```

🚨 **紧急预案 (Contingency Plan)**:

> 如果在**线上验证**步骤中发现任何问题（例如，安装失败、导入错误），说明发布的包是损坏的。**请立即中止发布流程**，并执行以下操作：
>
> 1.  登录 PyPI，找到该版本并**删除 (Delete)** 或**废弃 (Yank)** 它。
> 2.  回到本地，清理构建产物 (`rm -rf dist/`)，修复问题，然后从**阶段一**重新开始整个流程。
>     **切勿**继续进行下一阶段。

---

### **阶段三：官方发布定稿 (Official Release Finalization)**

**只有在阶段二的线上验证成功通过后**，才能进入此阶段。此阶段的目标是创建不可更改的 Git 记录，并正式官宣版本。

1.  **提交所有发布相关文件**:
    - 现在，我们确认一切正常，将所有修改（代码、文档、`pyproject.toml`, `poetry.lock`）提交到 Git。
      ```bash
      git add .
      git commit -m "chore(release): release v<新版本号>"
      ```
2.  **创建 Git 标签**:
    - 为这个已验证的提交创建一个对应的 Git 标签。
      ```bash
      git tag v<新版本号>
      ```
3.  **推送所有内容到远程仓库**:
    - 将主分支的提交和新标签一起推送到 GitHub。
      ```bash
      git push
      git push --tags
      ```

---

### **阶段四：社区沟通 (Communication)**

这是发布的最后一步，让社区知道您的新成果。

1.  **创建 GitHub Release**:
    - 在您的 GitHub 仓库页面，基于刚刚推送的标签（`v<新版本号>`）**创建 Release**。
    - 将 `CHANGELOG.md` 中对应版本的更新内容，作为 Release 的说明。
2.  **（可选）社区通知**:
    - 在相关渠道分享您的 GitHub Release 链接。

---

## **报告 Bug 或提交功能建议**

我们使用 [GitHub Issues](https://github.com/SakenW/trans-hub/issues) 来追踪所有的 Bug 和功能请求。

在提交 Issue 之前，请先搜索一下是否已经存在类似的 Issue。

- **对于 Bug 报告**: 请提供尽可能详细的信息，包括：您使用的 `Trans-Hub` 版本、Python 版本、操作系统、以及可以复现问题的最小代码片段和完整的错误堆栈。
- **对于功能建议**: 请清晰地描述您想要的功能，以及它能解决什么样的问题。

再次感谢您的贡献！我们期待与您共建 `Trans-Hub`。

---

## **附录：开发与测试脚本指南**

在 `Trans-Hub` 项目的根目录下，有几个非核心库的 Python 脚本，它们在开发、测试和演示中扮演着重要角色。

### `demo_complex_workflow.py` - 复杂工作流演示脚本

- **用途**: 这个脚本是 `Trans-Hub` 的**“活文档”和“教学演示”**。它旨在向人类用户（开发者、新贡献者）直观地展示 `Trans-Hub` 的各项核心功能。
- **如何运行**:
  ```bash
  poetry run python demo_complex_workflow.py
  ```

### `run_coordinator_test.py` - 端到端功能测试脚本

- **用途**: 这个脚本是项目的**“质量保证守门员”**。它通过程序化的方式，自动化地验证 `Trans-Hub` 的核心功能是否按预期工作。
- **如何运行**:
  ```bash
  poetry run python run_coordinator_test.py
  ```

### `tools/inspect_db.py` - 数据库检查工具

- **用途**: 这是一个轻量级的**辅助调试工具**，用于直观地查看数据库中的内容。
- **如何运行**:
  ```bash
  # 前提: 必须先运行 demo_complex_workflow.py 来生成数据库文件。
  poetry run python tools/inspect_db.py
  ```
