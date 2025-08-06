# tools/generate_project_snapshot.py
"""生成项目完整快照的工具，用于快速分享给AI协作伙伴。"""

import os
from pathlib import Path


def should_include_file(file_path: Path) -> bool:
    """判断是否应该包含该文件在快照中。

    Args:
        file_path: 文件路径。

    Returns:
        True表示包含，False表示排除。
    """
    # 排除隐藏文件和目录
    if any(part.startswith('.') for part in file_path.parts):
        return False

    # 排除特定目录
    excluded_dirs = {'docs', '__pycache__', '.git', '.pytest_cache', '.mypy_cache', '.vscode', '.github'}
    if any(part in excluded_dirs for part in file_path.parts):
        return False

    # 包含特定类型的文件
    included_extensions = {'.py', '.sql', '.toml', '.yml', '.yaml', '.rst', '.sh', '.json'}
    return file_path.suffix in included_extensions


def generate_snapshot(root_path: str = ".", output_file: str = "project_snapshot.txt") -> None:
    """生成项目快照文件。

    Args:
        root_path: 项目根目录路径。
        output_file: 输出文件名。
    """
    root = Path(root_path)
    output_path = root / "tools" / output_file

    with open(output_path, 'w', encoding='utf-8') as f:
        # 写入标题
        f.write("# Trans-Hub 项目完整快照\n\n")

        # 获取并写入目录结构
        f.write("## 目录结构\n\n")
        for path in sorted(root.rglob('*')):
            # 跳过输出文件本身
            if path.resolve() == output_path.resolve():
                continue

            # 排除隐藏文件和目录
            if any(part.startswith('.') for part in path.parts):
                continue

            # 排除特定目录
            excluded_dirs = {'docs', '__pycache__', '.git', '.pytest_cache', '.mypy_cache', '.vscode', '.github'}
            if any(part in excluded_dirs for part in path.parts):
                continue

            # 计算相对于根目录的层级
            relative_path = path.relative_to(root)
            depth = len(relative_path.parts) - 1
            indent = "  " * depth

            # 写入目录或文件
            if path.is_dir():
                f.write(f"{indent}- {path.name}/\n")
            else:
                f.write(f"{indent}- {path.name}\n")

        # 写入文件内容
        f.write("\n## 文件内容\n\n")

        # 收集所有需要包含的文件
        included_files = []
        for path in sorted(root.rglob('*')):
            # 跳过输出文件本身
            if path.resolve() == output_path.resolve():
                continue

            if path.is_file() and should_include_file(path):
                included_files.append(path)

        # 写入每个文件的内容
        for file_path in included_files:
            relative_path = file_path.relative_to(root)
            f.write(f"### {relative_path}\n\n")

            try:
                # 尝试以文本方式读取文件
                content = file_path.read_text(encoding='utf-8')
                # 规范化换行符
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                f.write(f"``````\n{content}\n``````\n\n")
            except Exception as e:
                f.write(f"``````\n[无法读取文件内容: {e}]\n``````\n\n")

    print(f"项目快照已生成: {output_path}")


def main() -> None:
    """主函数。"""
    print("正在生成项目快照...")
    generate_snapshot()


if __name__ == "__main__":
    main()