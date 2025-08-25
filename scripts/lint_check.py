# src/trans_hub/lint_check.py
"""统一的代码质量检查脚本。"""

import os
import subprocess
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger()


def run_command(command: list[str], description: str):
    """运行一个命令并检查其退出码。"""
    logger.info(f"🚀 Running: {description}...")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(
            f"❌ FAILED: {description}", 标准输出=result.stdout, 标准错误=result.stderr
        )
        print(result.stdout, file=sys.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    logger.info(f"✅ PASSED: {description}")
    logger.info("-" * 50)


def main():
    logger.info("=== Trans-Hub Code Quality Check ===")

    # 找到项目根目录 (包含 .importlinter 文件的目录)
    current_dir = Path.cwd()
    project_root = current_dir

    # 向上查找包含 .importlinter 的目录
    while project_root != project_root.parent:
        if (project_root / ".importlinter").exists():
            break
        project_root = project_root.parent
    else:
        logger.error("❌ 无法找到项目根目录 (.importlinter 文件)")
        sys.exit(1)

    # 切换到项目根目录
    original_cwd = os.getcwd()
    os.chdir(project_root)

    try:
        # 架构守护线 (在项目根目录运行)
        # 需要临时切换到 packages/server 目录来使用 poetry 环境，然后再切回项目根目录运行 lint-imports
        server_dir = project_root / "packages" / "server"
        os.chdir(server_dir)

        # 使用 poetry run 但在项目根目录运行 lint-imports
        import_linter_cmd = [
            "poetry",
            "run",
            "python",
            "-c",
            f"import os; os.chdir('{project_root}'); import subprocess; subprocess.run(['lint-imports'])",
        ]
        run_command(import_linter_cmd, "Import Linter")

        # 切换回项目根目录
        os.chdir(project_root)

        # 切换回 packages/server 目录进行其他检查
        server_dir = project_root / "packages" / "server"
        if server_dir.exists():
            os.chdir(server_dir)

        # 代码风格与格式化
        run_command(["poetry", "run", "ruff", "check", "."], "Ruff Check")
        run_command(
            ["poetry", "run", "ruff", "format", "--check", "."], "Ruff Format Check"
        )

        # 静态类型检查
        run_command(["poetry", "run", "mypy", "src/trans_hub"], "MyPy Type Check")

        logger.info("🎉 All checks passed successfully!")

    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)


if __name__ == "__main__":
    main()
