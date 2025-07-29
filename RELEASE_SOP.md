<!-- This file is auto-generated. Do not edit directly. -->
<!-- 此文件为自动生成，请勿直接编辑。 -->

<details open>
<summary><strong>English</strong></summary>

**English** | [简体中文](../../zh/root_files/RELEASE_SOP.md)

# Trans-Hub Releases Standard Operating Procedures (SOP)

> 🚨 **Note**: This process is only applicable to the core maintainers of the project.

This is a strict version release standard operating procedure prepared for the core maintainers of the `Trans-Hub` project. Please follow all steps in order to ensure the quality and reliability of each release.

### **Phase One: Local Preparation and Construction**

The goal of this stage is to prepare all artifacts to be released and conduct final validation locally.

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

**Current Status**: Your local codebase is ready for a technical release, but **no Git commits have been made yet**.

### **Phase Two: Technology Release and Validation**

The goal of this stage is to upload the package to PyPI and **immediately verify** its availability. This is the final quality checkpoint before the official announcement.

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

🚨 **Emergency Plan**:

If the `verify.py` script fails at any step, please immediately abort the release process and **yank** that version on PyPI, then restart from **Phase One**.

### **Stage Three: Official Release of Final Draft**

Only after successfully passing the online verification in phase two can one enter this stage.

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

### **Stage Four: Community Communication**

1.  **Create GitHub Release**:
    - On the GitHub repository page, **create a Release** based on the recently pushed tag.
    - Use the update content for the corresponding version in `CHANGELOG.md` as the description for the Release.
2.  **(Optional) Community Notification**:
    - Share your GitHub Release link on relevant channels.

</details>

<details>
<summary><strong>简体中文</strong></summary>

**English** | [简体中文](../../zh/root_files/RELEASE_SOP.md)

# Trans-Hub Releases Standard Operating Procedures (SOP)

> 🚨 **Note**: This process is only applicable to the core maintainers of the project.

This is a strict version release standard operating procedure prepared for the core maintainers of the `Trans-Hub` project. Please follow all steps in order to ensure the quality and reliability of each release.

### **Phase One: Local Preparation and Construction**

The goal of this stage is to prepare all artifacts to be released and conduct final validation locally.

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

**Current Status**: Your local codebase is ready for a technical release, but **no Git commits have been made yet**.

### **Phase Two: Technology Release and Validation**

The goal of this stage is to upload the package to PyPI and **immediately verify** its availability. This is the final quality checkpoint before the official announcement.

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

🚨 **Emergency Plan**:

If the `verify.py` script fails at any step, please immediately abort the release process and **yank** that version on PyPI, then restart from **Phase One**.

### **Stage Three: Official Release of Final Draft**

Only after successfully passing the online verification in phase two can one enter this stage.

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

### **Stage Four: Community Communication**

1.  **Create GitHub Release**:
    - On the GitHub repository page, **create a Release** based on the recently pushed tag.
    - Use the update content for the corresponding version in `CHANGELOG.md` as the description for the Release.
2.  **(Optional) Community Notification**:
    - Share your GitHub Release link on relevant channels.

</details>
