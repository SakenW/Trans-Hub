# Trans-Hub 发布标准作业流程 (SOP)

> 🚨 **注意**: 此流程仅适用于项目的核心维护者。

这是一个为 `Trans-Hub` 项目核心维护者准备的、严格的版本发布标准作业流程。请严格按照顺序执行所有步骤，以确保每个版本的质量和可靠性。

---

### **阶段一：本地准备与构建**

此阶段的目标是准备好所有待发布的工件 (Artifacts)，并在本地进行最终验证。

1.  **更新版本文件**:

    - **`pyproject.toml`**: 更新 `[tool.poetry]` 下的 `version` 字段为新版本号（例如 `2.2.0`）。
    - **`trans_hub/__init__.py`**: 同步更新 `__version__` 变量。

2.  **撰写更新日志**:

    - 在 **`CHANGELOG.md`** 文件顶部，为新版本添加详尽、清晰的变更记录。

3.  **审查相关文档**:

    - 检查 `README.md` 和 `docs/` 目录，确保所有文档内容与新版本功能同步。

4.  **更新依赖锁文件**:

    ```bash
    poetry lock
    ```

    > **原因**: 这确保了 `poetry.lock` 文件与 `pyproject.toml` 中的任何依赖或元数据变更完全同步。

5.  **最终本地验证 (CI/CD 最终检查标准)**:

    - 运行完整的代码质量检查和测试套件。

    ```bash
    poetry run ruff check . && poetry run mypy . && poetry run pytest
    ```

6.  **构建发布包**:
    ```bash
    poetry build
    ```
    > **结果**: 此命令会在 `dist/` 目录中创建最终的发布文件 (`.whl` 和 `.tar.gz`)。

**此刻状态**: 您的本地代码库已准备就绪，可以进行技术发布，但**尚未做任何 Git 提交**。

---

### **阶段二：技术发布与验证**

此阶段的目标是将软件包上传到 PyPI，并**立即验证**其可用性。这是在正式官宣前的最后一道质量关卡。

1.  **配置 PyPI 认证 (仅需一次)**:

    - 运行 `poetry config pypi-token.pypi <你的令牌>`。

2.  **执行技术发布**:

    ```bash
    poetry publish
    ```

3.  **立即进行线上验证 (关键步骤)**:

    - **检查 PyPI 页面**: 访问 `https://pypi.org/project/trans-hub/`，确认新版本已显示。
    - **在全新环境中测试安装**:

      ```bash
      # 1. 创建全新的、干净的虚拟环境
      cd ~ && rm -rf temp-pypi-test && mkdir temp-pypi-test && cd temp-pypi-test
      python -m venv .venv && source .venv/bin/activate

      # 2. 从 PyPI 安装刚刚发布的版本（包含所有 extras 以进行完整测试）
      pip install "trans-hub[translators,openai]==<新版本号>"

      # 3. 运行一个简单的验证脚本，确保核心功能正常
      #    (或者使用项目中的 verify.py 脚本)
      python -c "import asyncio, os; from trans_hub import *; from trans_hub.db.schema_manager import apply_migrations; DB_FILE='v.db'; async def r(): apply_migrations(DB_FILE); h=DefaultPersistenceHandler(DB_FILE); c=Coordinator(TransHubConfig(database_url=f'sqlite:///{os.path.abspath(DB_FILE)}'),h); await c.initialize(); print('OK!'); await c.close(); os.remove(DB_FILE); asyncio.run(r())"
      ```

🚨 **紧急预案**:

> 如果线上验证步骤中发现任何问题（安装失败、导入错误），请立即中止发布流程，并**废弃 (Yank)** PyPI 上的该版本，然后从**阶段一**重新开始。

---

### **阶段三：官方发布定稿**

**只有在阶段二的线上验证成功通过后**，才能进入此阶段。

1.  **提交所有发布相关文件**:

    - 现在，我们确认一切正常，将所有修改（包括代码、文档、`pyproject.toml`, `poetry.lock` 等）提交到 Git。

    ```bash
    git add .
    git commit -m "chore(release): Release v<新版本号>"
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

### **阶段四：社区沟通**

1.  **创建 GitHub Release**:
    - 在 GitHub 仓库页面，基于刚刚推送的标签**创建 Release**。
    - 将 `CHANGELOG.md` 中对应版本的更新内容，作为 Release 的说明。
2.  **(可选) 社区通知**:
    - 在相关渠道分享您的 GitHub Release 链接。
