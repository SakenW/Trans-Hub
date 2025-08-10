# tools/generate_project_snapshot.py
"""生成项目完整快照的工具，用于快速分享给AI协作伙伴。"""

import os
from pathlib import Path

# 定义需要排除的目录和文件
EXCLUDED_DIRS = {
    "docs",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".vscode",
    "dist",
    ".ruff_cache",
}
EXCLUDED_SUFFIXES = {".db", ".db-wal", ".db-shm"}

# 定义需要特别包含的隐藏文件和目录
INCLUDE_SPECIFIC_HIDDEN = {".env.example", "pyproject.toml", ".github/workflows/ci.yml"}

# 定义需要包含的文件类型
INCLUDE_SUFFIXES = {".py", ".sql"}


def should_include(path: Path, root_path: Path) -> bool:
    """判断是否应该包含该文件或目录在快照中。"""
    # 检查是否是特别包含的隐藏文件
    relative_path = path.relative_to(root_path)
    if str(relative_path) in INCLUDE_SPECIFIC_HIDDEN:
        return True

    # 排除隐藏文件和目录 (除了特别包含的)
    if (
        any(part.startswith(".") for part in path.parts)
        and str(relative_path) not in INCLUDE_SPECIFIC_HIDDEN
    ):
        return False

    # 排除特定目录
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return False

    # 排除特定文件类型
    if path.suffix in EXCLUDED_SUFFIXES:
        return False

    # 对于文件，确保它具有我们想要包含的后缀
    if path.is_file():
        return path.suffix in INCLUDE_SUFFIXES

    return True


def generate_snapshot(
    root_path: str = ".", output_file: str = "project_snapshot.txt"
) -> None:
    """生成项目快照文件。"""
    root = Path(root_path).resolve()
    # 确保输出到 tools 目录下
    output_dir = root / "tools"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / output_file

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Trans-Hub 项目完整快照\n\n")

        # 获取并写入目录结构（到最深层级）
        f.write("## 目录结构\n\n")
        # 使用 os.walk 确保遍历到最深层级
        for root_dir, dirs, files in os.walk(root):
            # 过滤掉不应该包含的目录
            dirs[:] = [
                d
                for d in dirs
                if not any(excluded in root_dir for excluded in EXCLUDED_DIRS)
                and d not in EXCLUDED_DIRS
            ]

            # 计算相对路径和缩进
            relative_path = Path(root_dir).relative_to(root)
            depth = len(relative_path.parts)
            indent = "  " * depth

            # 写入当前目录
            if depth > 0:
                f.write(f"{indent}- {Path(root_dir).name}/\n")

            # 写入文件
            for file in sorted(files):
                file_path = Path(root_dir) / file
                file_path.relative_to(root)
                if should_include(file_path, root):
                    file_indent = "  " * (depth + 1)
                    f.write(f"{file_indent}- {file}\n")

        # 写入文件内容
        f.write("\n## 文件内容\n\n")

        # 再次遍历以获取文件内容
        all_files = []
        for root_dir, _, files in os.walk(root):
            # 过滤掉不应该包含的目录
            if any(excluded in root_dir for excluded in EXCLUDED_DIRS):
                continue

            for file in files:
                file_path = Path(root_dir) / file
                if should_include(file_path, root):
                    all_files.append(file_path)

        # 按相对路径排序
        all_files.sort(key=lambda x: x.relative_to(root))

        for file_path in all_files:
            if file_path.resolve() == output_path.resolve():
                continue

            relative_path = file_path.relative_to(root)
            f.write(f"### {relative_path}\n\n")

            try:
                content = file_path.read_text(encoding="utf-8")
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                f.write(f"``````\n{content}\n``````\n\n")
            except Exception as e:
                f.write(f"``````\n[无法读取文件内容: {e}]\n``````\n\n")

    print(f"项目快照已生成: {output_path}")


def main() -> None:
    """主函数。"""
    print("正在生成项目快照...")
    # 项目根目录是当前文件的父目录的父目录
    project_root = Path(__file__).parent.parent
    generate_snapshot(str(project_root))


if __name__ == "__main__":
    main()
