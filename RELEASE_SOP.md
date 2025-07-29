<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->


<!-- English -->
# Trans-Hub Releases Standard Operating Procedures (SOP)

<!-- 简体中文 -->
# Trans-Hub 发布标准作业流程 (SOP)

---


<!-- English -->
> 🚨 **Note**: This process is only applicable to the core maintainers of the project.

<!-- 简体中文 -->
> 🚨 **注意**: 此流程仅适用于项目的核心维护者。

---


<!-- English -->
This is a strict version release standard operating procedure prepared for the core maintainers of the `Trans-Hub` project. Please follow all steps in order to ensure the quality and reliability of each release.

<!-- 简体中文 -->
这是一个为 `Trans-Hub` 项目核心维护者准备的、严格的版本发布标准作业流程。请严格按照顺序执行所有步骤，以确保每个版本的质量和可靠性。

---


<!-- English -->
### **Phase One: Local Preparation and Construction**

<!-- 简体中文 -->
### **阶段一：本地准备与构建**

---


<!-- English -->
The goal of this stage is to prepare all artifacts to be released and conduct final validation locally.

<!-- 简体中文 -->
此阶段的目标是准备好所有待发布的工件 (Artifacts)，并在本地进行最终验证。

---


<!-- English -->
1.  **Update Version Files**:

    - **`pyproject.toml`**: Update the `version` field under `[tool.poetry]` to the new version number (e.g., `2.2.0`).
    - **`trans_hub/__init__.py`**: Synchronize the `__version__` variable.

2.  **Write Change Log**:

    - At the top of the **`CHANGELOG.md`** file, add a detailed and clear change record for the new version.

3.  **Review Relevant Documentation**:

    - Check the `README.md` and `docs/` directory to ensure all documentation content is synchronized with the new version features.

4.  **Update Dependency Lock File**:

    ```bash
    poetry lock
    ```

    > **Reason**: This ensures that the `poetry.lock` file is fully synchronized with any changes in dependencies or metadata in `pyproject.toml`.

5.  **Final Local Validation (CI/CD Final Check Standards)**:

    - Run a complete code quality check and test suite.

    ```bash
    poetry run ruff check . && poetry run mypy . && poetry run pytest
    ```

6.  **Build Release Package**:
    ```bash
    poetry build
    ```
    > **Result**: This command will create the final release files (`.whl` and `.tar.gz`) in the `dist/` directory.

<!-- 简体中文 -->
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

---


<!-- English -->
**Current Status**: Your local codebase is ready for a technical release, but **no Git commits have been made yet**.

<!-- 简体中文 -->
**此刻状态**: 您的本地代码库已准备就绪，可以进行技术发布，但**尚未做任何 Git 提交**。

---


<!-- English -->
### **Phase Two: Technology Release and Validation**

<!-- 简体中文 -->
### **阶段二：技术发布与验证**

---


<!-- English -->
The goal of this stage is to upload the package to PyPI and **immediately verify** its availability. This is the final quality checkpoint before the official announcement.

<!-- 简体中文 -->
此阶段的目标是将软件包上传到 PyPI，并**立即验证**其可用性。这是在正式官宣前的最后一道质量关卡。

---


<!-- English -->
1.  **Configure PyPI Authentication (only needs to be done once)**:

    - Run `poetry config pypi-token.pypi <your token>`.

2.  **Perform Technical Release**:

    ```bash
    poetry publish
    ```

3.  **Immediate Online Verification (key step)**:

    - **Check PyPI Page**: Visit `https://pypi.org/project/trans-hub/` to confirm the new version is displayed.
    - **Test Installation and Core Functionality in a Fresh Environment**:

      ```bash
      # 1. Create a brand new, clean temporary directory and virtual environment
      cd ~ && rm -rf temp-pypi-test && mkdir temp-pypi-test && cd temp-pypi-test
      python -m venv .venv && source .venv/bin/activate

      # 2. Install the just-released version from PyPI (including all extras for full testing)
      pip install "trans-hub[translators,openai]==<new version number>"

      # 3. Create a temporary .env file for OpenAI engine initialization testing
      echo 'TH_OPENAI_API_KEY="dummy-key-for-verification"' > .env

      # 4. Create a verification script named verify.py
      touch verify.py
      ```

    - **Paste the following complete code into the `verify.py` file**:

      ```python
      # verify.py
      import asyncio
      import os
      import sys
      import structlog
      from dotenv import load_dotenv

      # Verify if extras are installed correctly
      try:
          import translators
          import openai
          print("✅ OK: 'translators' and 'openai' libraries are installed.")
      except ImportError as e:
          print(f"❌ FAILED: A required extra library is missing. Error: {e}")
          sys.exit(1)

      from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
      from trans_hub.db.schema_manager import apply_migrations
      from trans_hub.logging_config import setup_logging

      load_dotenv()
      setup_logging()
      log = structlog.get_logger()

      async def run_verification():
          log.info("--- Verifying Trans-Hub Package ---")
          DB_FILE = "verify_test.db"
          if os.path.exists(DB_FILE): os.remove(DB_FILE)
          apply_migrations(DB_FILE)

          handler = DefaultPersistenceHandler(DB_FILE)

          # Test default engine
          log.info("\nStep 1: Verifying default engine ('translators')...")
          try:
              config_translators = TransHubConfig(database_url=f"sqlite:///{os.path.abspath(DB_FILE)}")
              coord = Coordinator(config_translators, handler)
              await coord.initialize()
              await coord.close()
              log.info("✅ OK: Default engine initialized successfully.")
          except Exception as e:
              log.error("❌ FAILED", error=str(e), exc_info=True); sys.exit(1)

          # Test OpenAI engine
          log.info("\nStep 2: Verifying 'openai' engine can be activated...")
          try:
              config_openai = TransHubConfig(active_engine="openai", source_lang="en")
              coord = Coordinator(config_openai, handler)
              await coord.initialize()
              await coord.close()
              log.info("✅ OK: OpenAI engine initialized successfully.")
          except Exception as e:
              log.error("❌ FAILED", error=str(e), exc_info=True); sys.exit(1)

          if os.path.exists(DB_FILE): os.remove(DB_FILE)
          log.info("\n🎉 Verification successful! 🎉")

      asyncio.run(run_verification())
      ```

    - **Run the verification script**:
      ```bash
      python verify.py
      ```
    - **Clean up the environment**:
      ```bash
      deactivate
      cd ~ && rm -rf temp-pypi-test
      ```

<!-- 简体中文 -->
1.  **配置 PyPI 认证 (仅需一次)**:

    - 运行 `poetry config pypi-token.pypi <你的令牌>`。

2.  **执行技术发布**:

    ```bash
    poetry publish
    ```

3.  **立即进行线上验证 (关键步骤)**:

    - **检查 PyPI 页面**: 访问 `https://pypi.org/project/trans-hub/`，确认新版本已显示。
    - **在全新环境中测试安装与核心功能**:

      ```bash
      # 1. 创建一个全新的、干净的临时目录和虚拟环境
      cd ~ && rm -rf temp-pypi-test && mkdir temp-pypi-test && cd temp-pypi-test
      python -m venv .venv && source .venv/bin/activate

      # 2. 从 PyPI 安装刚刚发布的版本（包含所有 extras 以进行完整测试）
      pip install "trans-hub[translators,openai]==<新版本号>"

      # 3. 创建一个临时的 .env 文件以供 OpenAI 引擎初始化测试
      echo 'TH_OPENAI_API_KEY="dummy-key-for-verification"' > .env

      # 4. 创建一个名为 verify.py 的验证脚本
      touch verify.py
      ```

    - **将以下完整代码粘贴到 `verify.py` 文件中**:

      ```python
      # verify.py
      import asyncio
      import os
      import sys
      import structlog
      from dotenv import load_dotenv

      # 验证 extras 是否已正确安装
      try:
          import translators
          import openai
          print("✅ OK: 'translators' and 'openai' libraries are installed.")
      except ImportError as e:
          print(f"❌ FAILED: A required extra library is missing. Error: {e}")
          sys.exit(1)

      from trans_hub import Coordinator, DefaultPersistenceHandler, TransHubConfig
      from trans_hub.db.schema_manager import apply_migrations
      from trans_hub.logging_config import setup_logging

      load_dotenv()
      setup_logging()
      log = structlog.get_logger()

      async def run_verification():
          log.info("--- Verifying Trans-Hub Package ---")
          DB_FILE = "verify_test.db"
          if os.path.exists(DB_FILE): os.remove(DB_FILE)
          apply_migrations(DB_FILE)

          handler = DefaultPersistenceHandler(DB_FILE)

          # 测试默认引擎
          log.info("\nStep 1: Verifying default engine ('translators')...")
          try:
              config_translators = TransHubConfig(database_url=f"sqlite:///{os.path.abspath(DB_FILE)}")
              coord = Coordinator(config_translators, handler)
              await coord.initialize()
              await coord.close()
              log.info("✅ OK: Default engine initialized successfully.")
          except Exception as e:
              log.error("❌ FAILED", error=str(e), exc_info=True); sys.exit(1)

          # 测试 OpenAI 引擎
          log.info("\nStep 2: Verifying 'openai' engine can be activated...")
          try:
              config_openai = TransHubConfig(active_engine="openai", source_lang="en")
              coord = Coordinator(config_openai, handler)
              await coord.initialize()
              await coord.close()
              log.info("✅ OK: OpenAI engine initialized successfully.")
          except Exception as e:
              log.error("❌ FAILED", error=str(e), exc_info=True); sys.exit(1)

          if os.path.exists(DB_FILE): os.remove(DB_FILE)
          log.info("\n🎉 Verification successful! 🎉")

      asyncio.run(run_verification())
      ```

    - **运行验证脚本**:
      ```bash
      python verify.py
      ```
    - **清理环境**:
      ```bash
      deactivate
      cd ~ && rm -rf temp-pypi-test
      ```

---


<!-- English -->
🚨 **Emergency Plan**:

<!-- 简体中文 -->
🚨 **紧急预案**:

---


<!-- English -->
If the `verify.py` script fails at any step, please immediately abort the release process and **yank** that version on PyPI, then restart from **Phase One**.

<!-- 简体中文 -->
> 如果 `verify.py` 脚本在任何一步失败，请立即中止发布流程，并**废弃 (Yank)** PyPI 上的该版本，然后从**阶段一**重新开始。

---


<!-- English -->
### **Stage Three: Official Release of Final Draft**

<!-- 简体中文 -->
### **阶段三：官方发布定稿**

---


<!-- English -->
Only after successfully passing the online verification in phase two can one enter this stage.

<!-- 简体中文 -->
**只有在阶段二的线上验证成功通过后**，才能进入此阶段。

---


<!-- English -->
1.  **Submit all release-related documents**:

    - Now, we confirm that everything is normal and submit all modifications (including code, documentation, `pyproject.toml`, `poetry.lock`, etc.) to Git.

    ```bash
    git add .
    git commit -m "chore(release): Release v<new version number>"
    ```

2.  **Create Git tag**:

    - Create a corresponding Git tag for this verified commit.

    ```bash
    git tag v<new version number>
    ```

3.  **Push everything to the remote repository**:
    - Push the commits from the main branch and the new tag to GitHub.
    ```bash
    git push
    git push --tags
    ```

<!-- 简体中文 -->
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


<!-- English -->
### **Stage Four: Community Communication**

<!-- 简体中文 -->
### **阶段四：社区沟通**

---


<!-- English -->
1.  **Create GitHub Release**:
    - On the GitHub repository page, **create a Release** based on the recently pushed tag.
    - Use the update content for the corresponding version in `CHANGELOG.md` as the description for the Release.
2.  **(Optional) Community Notification**:
    - Share your GitHub Release link on relevant channels.

<!-- 简体中文 -->
1.  **创建 GitHub Release**:
    - 在 GitHub 仓库页面，基于刚刚推送的标签**创建 Release**。
    - 将 `CHANGELOG.md` 中对应版本的更新内容，作为 Release 的说明。
2.  **(可选) 社区通知**:
    - 在相关渠道分享您的 GitHub Release 链接。
