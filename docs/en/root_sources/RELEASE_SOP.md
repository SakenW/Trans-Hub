# Trans-Hub Releases Standard Operating Procedures (SOP)

> 🚨 **Note**: This process is only applicable to the core maintainers of the project.

This is a strict version release standard operating procedure prepared for the core maintainers of the `Trans-Hub` project. Please follow all steps in order to ensure the quality and reliability of each release.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

### **Phase One: Local Preparation and Construction**

The goal of this stage is to prepare all artifacts to be released and conduct final validation locally.

1. **Update version file:**

    - **`pyproject.toml`**: Update the `version` field under `[tool.poetry]` to the new version number (e.g., `2.2.0`).
    - **`trans_hub/__init__.py`**: Synchronize the `__version__` variable.

2. **Write update log:**

    - At the top of the **`CHANGELOG.md`** file, add detailed and clear change logs for the new version.

3. **Review relevant documents:**

    - Check the `README.md` and `docs/` directory to ensure that all documentation content is in sync with the new version features.

4. **Update dependency lock file:**

    ```bash
    poetry lock
    ```

    > **Reason**: This ensures that the `poetry.lock` file is fully synchronized with any changes in dependencies or metadata in `pyproject.toml`.

5. **Final Local Verification (CI/CD Final Inspection Standards):**

    - Run a complete code quality check and test suite.

    ```bash
    poetry run ruff check . && poetry run mypy . && poetry run pytest
    ```

6.  **Build the release package**:
    ```bash
    poetry build
    ```
    > **Result**: This command will create the final release files (`.whl` and `.tar.gz`) in the `dist/` directory.

**Current Status**: Your local codebase is ready for a technical release, but **no Git commits have been made yet**.

It seems there is no text provided for translation. Please provide the text you would like to have translated.

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
          log.info("It seems there is no text provided for translation. Please provide the text you would like to have translated. Verifying Trans-Hub Package It seems there is no text provided for translation. Please provide the text you would like to have translated.")
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

It seems there is no text provided for translation. Please provide the text you would like to have translated.

### **Stage Three: Official Release of Final Draft**

Only after successfully passing the online verification in Phase Two can one enter this stage.

1. **Submit all publication-related documents:**

    - Now, we confirm that everything is normal and will submit all modifications (including code, documentation, `pyproject.toml`, `poetry.lock`, etc.) to Git.

    ```bash
    git add .
    git commit -m "chore(release): Release v<新版本号>"
    ```

2. **Create Git Tag:**

    - Create a corresponding Git tag for this verified commit.

    ```bash
    git tag v<新版本号>
    ```

3. **Push all content to the remote repository**:
   - Push the commits from the main branch along with the new tags to GitHub.
   ```bash
   git push
   git push --tags
   ```

It seems there is no text provided for translation. Please provide the text you would like to have translated.

### **Stage Four: Community Communication**

1.  **Create GitHub Release**:
    - On the GitHub repository page, **create a Release** based on the tag you just pushed.
    - Use the update content for the corresponding version in `CHANGELOG.md` as the description for the Release.
2.  **(Optional) Community Notification**:
    - Share your GitHub Release link on relevant channels.
