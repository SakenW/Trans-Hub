# tools/rebuild_tests.py
"""
一个自动化工具，用于清理过时的测试文件并为 UIDA 架构重建新的测试目录结构。

本脚本遵循《技术宪章》，通过自动化确保测试迁移的一致性和可重复性。

运行方式 (在项目根目录):
  poetry run python tools/rebuild_tests.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

# 定义项目根目录
ROOT_DIR = Path(__file__).parent.parent.resolve()
TESTS_DIR = ROOT_DIR / "tests"


def log_info(message: str) -> None:
    """打印蓝色信息日志。"""
    print(f"\033[94m[INFO]\033[0m {message}")


def log_warn(message: str) -> None:
    """打印黄色警告日志。"""
    print(f"\033[93m[WARN]\033[0m {message}")


def log_success(message: str) -> None:
    """打印绿色成功日志。"""
    print(f"\033[92m[SUCCESS]\033[0m {message}")


def clean_old_test_files():
    """
    安全地删除所有旧的、基于 `business_id` 的测试文件。
    保留 `__init__.py` 和 `conftest.py`。
    """
    log_info("--- 开始清理旧的测试文件 ---")
    deleted_count = 0
    search_dirs = [TESTS_DIR / "unit", TESTS_DIR / "integration"]

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            log_warn(f"目录不存在，跳过清理: {search_dir}")
            continue

        log_info(f"正在扫描目录: {search_dir}")
        for path in search_dir.glob("**/*.py"):
            if path.name.startswith("test_") and path.is_file():
                log_warn(f"  - 正在删除: {path.relative_to(ROOT_DIR)}")
                path.unlink()
                deleted_count += 1

    # 清理空的旧子目录，例如 tests/unit/engines
    for search_dir in search_dirs:
        for path in list(search_dir.glob("*")):
            if path.is_dir() and not any(path.iterdir()):
                log_warn(f"  - 正在删除空目录: {path.relative_to(ROOT_DIR)}")
                path.rmdir()

    log_success(f"--- 清理完成，共删除了 {deleted_count} 个旧测试文件 ---")


def create_new_test_structure():
    """
    创建 UIDA 架构所需的全新测试目录和占位符文件。
    """
    log_info("\n--- 开始创建新的 UIDA 测试结构 ---")

    # 定义新的目录和文件结构
    structure = {
        "helpers": {
            "__init__.py": "# tests/helpers/__init__.py\n\"\"\"测试助手模块，提供数据工厂和生命周期管理器。\"\"\"\n",
            "factories.py": "# tests/helpers/factories.py\n\"\"\"负责创建可预测的测试数据。\"\"\"\n\n# TODO: 在此实现 create_uida_request_data 等工厂函数\n",
            "lifecycle.py": "# tests/helpers/lifecycle.py\n\"\"\"负责执行端到端的业务流程。\"\"\"\n\n# TODO: 在此实现 TestLifecycleManager 类\n",
        },
        "unit": {
            "_uida": {
                "__init__.py": "",
                "test_encoder.py": "# tests/unit/_uida/test_encoder.py\n\"\"\"测试 UIDA 编码器和规范化逻辑。\"\"\"\n\n# TODO: 添加对 JCS/I-JSON 和哈希的单元测试\n",
                "test_reuse_key.py": "# tests/unit/_uida/test_reuse_key.py\n\"\"\"测试复用键的生成和策略应用。\"\"\"\n\n# TODO: 添加对复用键生成的单元测试\n",
            },
            "_tm": {
                "__init__.py": "",
                "test_normalizers.py": "# tests/unit/_tm/test_normalizers.py\n\"\"\"测试文本归一化逻辑。\"\"\"\n\n# TODO: 添加对 normalize_plain_text_for_reuse 的单元测试\n",
            },
        },
        "integration": {
            "test_persistence_uida.py": "# tests/integration/test_persistence_uida.py\n\"\"\"对 UIDA 持久化层的集成测试。\"\"\"\n\n# TODO: 添加对 upsert_content, find_tm_entry 等的集成测试\n",
            "test_coordinator_uida.py": "# tests/integration/test_coordinator_uida.py\n\"\"\"对 UIDA Coordinator 端到端流程的集成测试。\"\"\"\n\n# TODO: 使用 helpers/factories.py 和 helpers/lifecycle.py 编写高级集成测试\n",
        },
    }

    # 递归地创建目录和文件
    def create_recursively(base_path: Path, struct: dict):
        for name, content in struct.items():
            path = base_path / name
            if isinstance(content, dict):
                log_info(f"  - 正在创建目录: {path.relative_to(ROOT_DIR)}")
                path.mkdir(exist_ok=True)
                create_recursively(path, content)
            elif isinstance(content, str):
                log_info(f"  - 正在创建文件: {path.relative_to(ROOT_DIR)}")
                path.write_text(content, encoding="utf-8")

    create_recursively(TESTS_DIR, structure)

    log_success("--- 新的 UIDA 测试结构创建完成 ---")


def main():
    """执行清理和重建的主函数。"""
    print("==============================================")
    print("  Trans-Hub 测试目录 UIDA 架构重建工具  ")
    print("==============================================")

    if not TESTS_DIR.is_dir():
        log_warn(f"测试目录 '{TESTS_DIR}' 不存在，跳过。")
        return

    clean_old_test_files()
    create_new_test_structure()

    print("\n操作完成。现在可以开始在新的占位符文件中编写 UIDA 测试了。")


if __name__ == "__main__":
    main()