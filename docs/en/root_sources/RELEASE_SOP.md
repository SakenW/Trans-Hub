# Trans-Hub Releases Standard Operating Procedures (SOP)

> 🚨 **Note**: This process is only applicable to the core maintainers of the project.

This is a strict version release standard operating procedure prepared for the core maintainers of the `Trans-Hub` project. Please follow all steps in order to ensure the quality and reliability of each release.

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

### **Phase Two: Technology Release and Verification**

The goal of this stage is to upload the package to PyPI and **immediately verify** its availability. This is the final quality checkpoint before the official announcement.

1. **Configure PyPI authentication (only needs to be done once):**

    - Run `poetry config pypi-token.pypi <your token>`.

2. **Implementation of Technical Release:**

    ```bash
    poetry publish
    ```

3. **Immediately conduct online verification (key step)**:

    - **Check the PyPI page**: Visit `https://pypi.org/project/trans-hub/` to confirm that the new version is displayed.
    - **Test installation and core functionality in a new environment**:

      ```bash
      # 1. 创建一个全新的、干净的临时目录和虚拟环境
      cd ~ && rm -rf temp-pypi-test && mkdir temp-pypi-test && cd temp-pypi-test
      python -m venv .venv && source .venv/bin/activate

      # 2. Install the newly released version from PyPI (including all extras for complete testing)  
      pip install "trans-hub[translators,openai]==<new version number>

      # 3. Create a temporary .env file for OpenAI engine initialization testing
      echo 'TH_OPENAI_API_KEY="dummy-key-for-verification"' > .env

      # 4. Create a verification script named verify.py
      touch verify.py
      ```

    - **Paste the following complete code into the `verify.py` file:**

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

          # Test Default Engine
log.info("\nStep 1: Verifying default engine ('translators')...")
try:
    config_translators = TransHubConfig(database_url=f"sqlite:///{os.path.abspath(DB_FILE)}")
    coord = Coordinator(config_translators, handler)
    await coord.initialize()
    await coord.close()
    log.info("✅ OK: Default engine initialized successfully.")
except Exception as e:
    log.error("❌ FAILED", error=str(e), exc_info=True); sys.exit(1)

          # Test OpenAI Engine
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

    - **Run the verification script**:
      ```bash
      python verify.py
      ```
    - **Clean up the environment**:
      ```bash
      deactivate
      cd ~ && rm -rf temp-pypi-test
      ```

🚨 **Emergency Plan**:

If the `verify.py` script fails at any step, please immediately abort the release process and **yank** that version on PyPI, then restart from **Phase One**.

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

### **Stage Four: Community Communication**

1.  **Create GitHub Release**:
    - On the GitHub repository page, **create a Release** based on the tag you just pushed.
    - Use the update content for the corresponding version in `CHANGELOG.md` as the description for the Release.
2.  **(Optional) Community Notification**:
    - Share your GitHub Release link on relevant channels.
