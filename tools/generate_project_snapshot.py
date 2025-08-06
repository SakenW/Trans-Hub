# tools/generate_project_snapshot.py
"""生成项目完整快照的工具，用于快速分享给AI协作伙伴。"""

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
}
EXCLUDED_SUFFIXES = {".db", ".db-wal", ".db-shm"}

# 定义需要特别包含的隐藏文件和目录
INCLUDE_SPECIFIC_HIDDEN = {".env.example", "pyproject.toml", ".github/workflows/ci.yml"}


def should_include(path: Path, root_path: Path) -> bool:
    """判断是否应该包含该文件或目录在快照中。"""
    # 检查是否是特别包含的隐藏文件
    relative_path = path.relative_to(root_path)
    if str(relative_path) in INCLUDE_SPECIFIC_HIDDEN:
        return True

    # 排除隐藏文件和目录
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

    return True


def generate_snapshot(
    root_path: str = ".", output_file: str = "project_snapshot.txt"
) -> None:
    """生成项目快照文件。"""
    root = Path(root_path)
    # 修正输出路径，确保脚本在任何地方运行都能找到正确位置
    output_path = root / "project_snapshot.txt"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Trans-Hub 项目完整快照\n\n")

        # 获取并写入目录结构
        f.write("## 目录结构\n\n")
        all_paths = sorted(root.rglob("*"))

        for path in all_paths:
            if path.resolve() == output_path.resolve():
                continue
            if not should_include(path, root):
                continue

            relative_path = path.relative_to(root)
            depth = len(relative_path.parts) - 1
            indent = "  " * depth

            if path.is_dir():
                f.write(f"{indent}- {path.name}/\n")
            else:
                f.write(f"{indent}- {path.name}\n")

        # 写入文件内容
        f.write("\n## 文件内容\n\n")

        for file_path in all_paths:
            if file_path.resolve() == output_path.resolve():
                continue
            if not file_path.is_file() or not should_include(file_path, root):
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
    # 修正：从脚本所在目录的上级目录开始生成
    project_root = Path(__file__).parent.parent
    generate_snapshot(str(project_root))


if __name__ == "__main__":
    main()
