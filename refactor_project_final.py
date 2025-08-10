# refactor_project_final_v3.py
import os
import subprocess
import sys
from pathlib import Path

# --- 配置 ---
# 设置为 True 可以预览所有将要执行的命令，而不会实际操作文件或 Git
DRY_RUN = False

ROOT_DIR = Path(__file__).parent.resolve()
ARCHIVE_DIR_NAME = "_archive_DO_NOT_USE"

# --- 日志和命令执行 ---
class Color:
    BLUE, GREEN, YELLOW, RED, END = '\033[94m', '\033[92m', '\033[93m', '\033[91m', '\033[0m'

def log(message, color=Color.BLUE, indent=0):
    print(f"{'  ' * indent}{color}●{Color.END} {message}")

def run_command(cmd_list):
    """Executes a command, provides real-time feedback, and aborts on failure."""
    log(f"Executing: {' '.join(cmd_list)}", color=Color.YELLOW)
    if DRY_RUN:
        return
    try:
        result = subprocess.run(cmd_list, check=True, text=True, cwd=ROOT_DIR, capture_output=True)
    except subprocess.CalledProcessError as e:
        log(f"Command failed with exit code {e.returncode}:", color=Color.RED)
        log(f"STDOUT:\n{e.stdout}", color=Color.RED, indent=1)
        log(f"STDERR:\n{e.stderr}", color=Color.RED, indent=1)
        log("Refactoring aborted. It's recommended to restore your workspace with `git reset --hard`.", color=Color.RED)
        sys.exit(1)

# --- 新架构定义 (省略以保持简洁) ---
PACKAGE_STRUCTURE = { "core": {"src_dir": "src/trans_hub_core", "pytyped": True}, "uida": {"src_dir": "src/trans_hub_uida", "pytyped": True}, "server": {"src_dir": "src/trans_hub", "pytyped": True}, "sdk": {"src_dir": "src/trans_hub_sdk", "pytyped": False}}
FILE_MAPPING = {"trans_hub/core/exceptions.py": "packages/core/src/trans_hub_core/exceptions.py", "trans_hub/core/interfaces.py": "packages/core/src/trans_hub_core/interfaces.py", "trans_hub/core/types.py": "packages/core/src/trans_hub_core/types.py", "trans_hub/utils.py": "packages/core/src/trans_hub_core/utils.py", "trans_hub/_uida/encoder.py": "packages/uida/src/trans_hub_uida/uida.py", "trans_hub/_uida/reuse_key.py": "packages/uida/src/trans_hub_uida/uida.py", "alembic/versions/3f8b9e6a0c2c_initial_schema.py": "packages/server/alembic/versions/3f8b9e6a0c2c_initial_schema.py", "examples/01_core_workflow.py": "packages/server/examples/01_core_workflow.py", "examples/_shared.py": "packages/server/examples/_shared.py", "tests/helpers/factories.py": "packages/server/tests/helpers/factories.py", "tests/integration/test_persistence_uida.py": "packages/server/tests/integration/db/test_persistence_postgres.py", "tests/integration/test_coordinator_uida.py": "packages/server/tests/integration/end2end/test_coordinator_flow.py", "tests/unit/_uida/test_encoder.py": "packages/server/tests/unit/uida/test_uida_contract.py", "tests/unit/_tm/test_normalizers.py": "packages/server/tests/unit/domain/test_tm_basics.py", "tools/inspect_db.py": "packages/server/tools/inspect_db.py", "trans_hub/config.py": "packages/server/src/trans_hub/config.py", "trans_hub/coordinator.py": "packages/server/src/trans_hub/application/coordinator.py", "trans_hub/policies/processing.py": "packages/server/src/trans_hub/application/processors.py", "trans_hub/_tm/normalizers.py": "packages/server/src/trans_hub/domain/tm.py", "trans_hub/db/schema.py": "packages/server/src/trans_hub/infrastructure/db/_schema.py", "trans_hub/persistence/__init__.py": "packages/server/src/trans_hub/infrastructure/persistence/__init__.py", "trans_hub/persistence/base.py": "packages/server/src/trans_hub/infrastructure/db/_base.py", "trans_hub/persistence/postgres.py": "packages/server/src/trans_hub/infrastructure/persistence/_postgres.py", "trans_hub/persistence/sqlite.py": "packages/server/src/trans_hub/infrastructure/persistence/_sqlite.py", "trans_hub/rate_limiter.py": "packages/server/src/trans_hub/infrastructure/redis/rate_limiter.py", "trans_hub/logging_config.py": "packages/server/src/trans_hub/observability/logging_config.py", "trans_hub/cli/main.py": "packages/server/src/trans_hub/presentation/cli/main.py", "trans_hub/cli/db.py": "packages/server/src/trans_hub/presentation/cli/commands/db.py", "trans_hub/cli/request.py": "packages/server/src/trans_hub/presentation/cli/commands/request.py", "trans_hub/cli/status.py": "packages/server/src/trans_hub/presentation/cli/commands/status.py"}
PLACEHOLDER_FILES = {}
PYPROJECT_TEMPLATE = "[build-system]\nrequires = [\"poetry-core>=1.0.0\"]\nbuild-backend = \"poetry.core.masonry.api\"\n\n[tool.poetry]\nname = \"trans-hub-{package_name}\"\nversion = \"0.1.0\"\ndescription = \"\"\nauthors = [\"Your Name <you@example.com>\"]\n\n[tool.poetry.dependencies]\npython = \">=3.10, <3.14\"\n"
OLD_SOURCE_ROOTS_TO_ARCHIVE = ["trans_hub", "alembic", "tests", "examples", "tools", ".trae", "docs", ".github", "alembic.ini", ".readthedocs.yaml"]
ROOT_ITEMS_TO_KEEP = {".git", ".gitignore", ".gitattributes", "pyproject.toml", ".env.example", "README.md", Path(__file__).name}


def perform_refactor():
    log("Starting project refactoring (v_final_3 - Direct Execution)...", color=Color.YELLOW)

    # --- STAGE 1: Create ALL necessary directories first ---
    log("Stage 1: Dynamically creating all target directories...", color=Color.GREEN)
    dirs_to_create = {
        ROOT_DIR / ARCHIVE_DIR_NAME,
        ROOT_DIR / "packages",
    }
    for new_path_str in FILE_MAPPING.values():
        dirs_to_create.add((ROOT_DIR / new_path_str).parent)

    for d in sorted(list(dirs_to_create)):
        log(f"Creating dir: {d.relative_to(ROOT_DIR)}", indent=1)
        if not DRY_RUN:
            d.mkdir(parents=True, exist_ok=True)

    # --- STAGE 2: Copy and merge content to new locations ---
    log("Stage 2: Copying and merging file content...", color=Color.GREEN)
    merge_targets = {}
    for old, new in FILE_MAPPING.items():
        if new not in merge_targets: merge_targets[new] = []
        merge_targets[new].append(old)
    
    for new_path_str, old_paths in sorted(merge_targets.items()):
        new_path = ROOT_DIR / new_path_str
        log(f"Writing to: {new_path_str}", indent=1)
        if not DRY_RUN:
            with open(new_path, "w", encoding="utf-8") as f:
                for i, p_str in enumerate(old_paths):
                    p = ROOT_DIR / p_str
                    if p.exists():
                        if i > 0: f.write(f"\n\n# --- Merged from: {p_str} ---\n")
                        f.write(p.read_text(encoding="utf-8"))

    # --- STAGE 3: Inform Git about the changes ---
    log("Stage 3: Informing Git of file changes (add/rm)...", color=Color.GREEN)
    for new_path_str, old_paths in sorted(merge_targets.items()):
        run_command(["git", "add", new_path_str])
        for old_path_str in old_paths:
             if (ROOT_DIR / old_path_str).exists():
                run_command(["git", "rm", old_path_str])
    
    # --- STAGE 4: Archive specific old source directories ---
    log("Stage 4: Archiving specific old source directories...", color=Color.GREEN)
    items_to_move = [item for item in OLD_SOURCE_ROOTS_TO_ARCHIVE if (ROOT_DIR / item).exists()]
    
    if items_to_move:
        run_command(["git", "mv"] + items_to_move + [ARCHIVE_DIR_NAME + "/"])
    else:
        log("No specific old source directories found to archive.", indent=1)

    log("Project refactoring completed successfully!", color=Color.GREEN)
    print("\n" + "="*50)
    log("Final check:", color=Color.YELLOW)
    print(f"  1. Old source code has been moved to `{ARCHIVE_DIR_NAME}`.")
    print(f"  2. The new structure is in `packages/`. Untracked cache directories may remain.")
    print(f"  3. Please run `git status`, then commit the changes.")

def main():
    if not (ROOT_DIR / ".git").is_dir():
        log("Error: This script must be run from the root of a Git repository.", color=Color.RED)
        return
    
    git_status_output = os.popen('git status --porcelain').read().strip()
    script_name = Path(__file__).name
    is_script_only_change = len(git_status_output.splitlines()) == 1 and git_status_output.endswith(script_name)
    
    if git_status_output and not is_script_only_change:
        log("Error: Your Git working directory is not clean. Please commit or stash your changes first.", color=Color.RED)
        print("`git status` output:")
        print(git_status_output)
        return
        
    log("Your Git working directory is clean, ready for refactoring.")
    if DRY_RUN:
        log("!!! DRY RUN mode is enabled. No actual commands will be executed. !!!", color=Color.YELLOW)
    
    confirm = input("Are you sure you want to start the refactoring? (yes/no): ")
    if confirm.lower() == 'yes':
        if is_script_only_change:
             run_command(["git", "add", script_name])
        perform_refactor()
    else:
        print("Operation cancelled.")

if __name__ == "__main__":
    main()