# packages/server/migrate_tests_structure.py
"""
Trans-Hub 测试目录结构自动化迁移脚本 (v1.0)

本脚本用于将旧的测试目录结构安全、幂等地迁移到最终的权威蓝图。

执行方式:
1. 将此脚本放置在 `packages/server/` 目录下。
2. 从 `packages/server/` 目录运行: `python migrate_tests_structure.py`
"""
from __future__ import annotations

import shutil
from pathlib import Path

# --- 配置 ---

# 假定脚本在 `packages/server/` 目录下运行
SERVER_ROOT = Path(__file__).parent.resolve()
TESTS_ROOT = SERVER_ROOT / "tests"

# 定义新目录结构
NEW_DIRS = [
    "helpers/factories",
    "helpers/tools",
    "unit/domain",
    "integration/application",
    "integration/domain",
    "integration/infrastructure/db/invariants",
    "integration/infrastructure/db/migrations",
    "integration/infrastructure/db/orm",
    "integration/infrastructure/db/repository",
    "integration/engines",
    "integration/workers",
    "e2e/cli/__snapshots__",
]

# 定义文件移动和重命名的映射关系
# (源路径: 目标路径)，路径相对于 TESTS_ROOT
MOVE_MAP = {
    # helpers
    "helpers/db_manager.py": "helpers/tools/db_manager.py",
    "helpers/factories.py": "helpers/factories/request_factory.py", # 假设旧的 factories.py 主要是 request factory
    # unit
    "unit/domain/test_tm_basics.py": "unit/domain/test_tm_properties.py",
    # integration
    "integration/end2end/test_coordinator_flow.py": "integration/application/test_app_flow.py",
    "integration/migrations/test_migrations_smoke.py": "integration/infrastructure/db/migrations/test_migrations_cycle.py",
    "integration/persistence/test_persistence.py": "integration/infrastructure/db/repository/test_persistence_transactions.py",
    "integration/worker/test_worker_flow.py": "integration/workers/test_worker_run_once.py",
    # e2e
    "integration/cli/test_cli_flow.py": "e2e/cli/test_cli_smoke_flow.py",
}

# 需要创建的新占位文件/配置文件
NEW_FILES = {
    "pytest.ini": """[pytest]
# https://docs.pytest.org/en/latest/reference/customize.html#ini-options-ref
addopts = -ra -q
testpaths = tests
markers =
    unit: Mark a test as a unit test (fast, no I/O).
    integration: Mark a test as an integration test (can use local DB/cache).
    e2e: Mark a test as an end-to-end test (from external boundary).
    db: Mark a test as database-dependent.
    slow: Mark a test as slow to run.
    migrations: Mark a test related to Alembic migrations.
    invariants: Mark a test that checks architectural invariants.
    engine: Mark a test related to translation engines.
    tm: Mark a test related to translation memory logic.
""",
    "README.md": "# Trans-Hub Server Tests\n\nThis directory contains all tests for the `trans-hub-server` package...",
    "unit/domain/README.md": "# Domain Unit Tests\n\nTests for pure domain logic with no I/O.",
    "integration/README.md": "# Integration Tests\n\nTests for component collaboration.",
    "e2e/README.md": "# End-to-End Tests\n\nThin layer of smoke tests from external boundaries.",
    "helpers/factories/content_factory.py": "# Content Factory: Create Content, Revision, Head objects.",
    "helpers/factories/tm_factory.py": "# TM Factory: Create TM Units, Links objects.",
    "helpers/tools/fakes.py": "# Test Doubles: FakeEngine, FakeCache, etc.",
    "helpers/tools/snapshot.py": "# Snapshot testing utility.",
    "integration/domain/test_resolver_with_cache.py": "# Tests for TranslationResolver with cache integration.",
    "integration/infrastructure/db/invariants/test_invariants_rls.py": "# Tests for Row-Level Security invariants.",
    "integration/infrastructure/db/orm/test_orm_mapping.py": "# Tests for SQLAlchemy ORM mapping.",
    "integration/engines/test_engine_factory_discovery.py": "# Tests for engine factory discovery mechanism.",
}

# 操作完成后需要被清理的旧目录
OLD_DIRS_TO_CLEAN = [
    "integration/cli",
    "integration/end2end",
    "integration/migrations",
    "integration/persistence",
    "integration/worker",
]

def main():
    """执行重构脚本。"""
    print("🚀 Starting automated migration of the test directory structure...")
    
    if not TESTS_ROOT.is_dir():
        print(f"❌ ERROR: Test root directory not found at {TESTS_ROOT}")
        return

    # 1. 创建所有新的目标目录
    print("\n[1/5] Creating new directory structure...")
    for dir_rel in NEW_DIRS:
        dir_abs = TESTS_ROOT / dir_rel
        dir_abs.mkdir(parents=True, exist_ok=True)
        print(f"  - Ensured directory exists: {dir_rel}")

    # 2. 移动并重命名文件
    print("\n[2/5] Moving and renaming test files...")
    for src_rel, dest_rel in MOVE_MAP.items():
        src_abs = TESTS_ROOT / src_rel
        dest_abs = TESTS_ROOT / dest_rel

        if not src_abs.exists():
            if dest_abs.exists():
                print(f"  - [SKIP] Source '{src_rel}' not found, but destination '{dest_rel}' already exists.")
            else:
                print(f"  - [WARN] Source '{src_rel}' not found. Cannot move.")
            continue
        
        try:
            shutil.move(str(src_abs), str(dest_abs))
            print(f"  - [OK] Moved: {src_rel} -> {dest_rel}")
        except Exception as e:
            print(f"  - [FAIL] Could not move '{src_rel}': {e}")

    # 3. 创建新的占位/配置文件
    print("\n[3/5] Creating new placeholder files and configurations...")
    for file_rel, content in NEW_FILES.items():
        file_abs = (TESTS_ROOT / file_rel) if file_rel != "pytest.ini" else (SERVER_ROOT / file_rel)
        if file_abs.exists():
            print(f"  - [SKIP] File '{file_rel}' already exists.")
            continue
        
        try:
            file_abs.write_text(content.strip() + "\n", encoding="utf-8")
            print(f"  - [OK] Created: {file_rel}")
        except Exception as e:
            print(f"  - [FAIL] Could not create '{file_rel}': {e}")

    # 4. 确保所有目录都有 __init__.py
    print("\n[4/5] Ensuring all directories are Python packages...")
    for d in TESTS_ROOT.rglob("*"):
        if d.is_dir() and not (d.name.startswith('.') or d.name == '__pycache__' or d.name == '__snapshots__'):
            init_py = d / "__init__.py"
            if not init_py.exists():
                init_py.touch()
                print(f"  - [OK] Created: {init_py.relative_to(TESTS_ROOT)}")

    # 5. 清理旧的、现在应该为空的目录
    print("\n[5/5] Cleaning up old directories...")
    for dir_rel in OLD_DIRS_TO_CLEAN:
        dir_abs = TESTS_ROOT / dir_rel
        if not dir_abs.is_dir():
            print(f"  - [SKIP] Directory '{dir_rel}' does not exist.")
            continue
        
        try:
            if not any(dir_abs.iterdir()):
                dir_abs.rmdir()
                print(f"  - [OK] Removed empty directory: {dir_rel}")
            else:
                print(f"  - [WARN] Directory '{dir_rel}' is not empty. Please review and remove manually.")
        except Exception as e:
            print(f"  - [FAIL] Could not remove directory '{dir_rel}': {e}")

    print("\n✅ Migration complete!")
    print("Please review the changes with your version control system (e.g., `git status`).")

if __name__ == "__main__":
    main()