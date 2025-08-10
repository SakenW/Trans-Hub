#!/usr/bin/env python3
# scripts/generate_snapshot.py
"""
一个用于生成 Trans-Hub Monorepo 项目完整快照的工具。
(v4 - 增加 lock 文件排除)
"""
import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import IO

try:
    from rich.console import Console
except ImportError:
    print("错误: 本脚本需要 'rich' 库。请在 server 包中运行: poetry add rich --group dev")
    exit(1)

# --- 配置项 ---
DEFAULT_PACKAGES_DIRS = ["packages/core", "packages/uida", "packages/server"]
ROOT_FILES_TO_INCLUDE = [
    ".env.example", "pyproject.toml", "README.md",
    "packages/server/alembic.ini", "scripts/generate_snapshot.py"
]
# [修复] 将 poetry.lock 添加到排除列表
EXCLUDE_PATTERNS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache",
    ".vscode", "dist", ".ruff_cache", ".venv",
    "node_modules", ".DS_Store", "poetry.lock"
}

def find_project_root(start_path: Path = Path('.')) -> Path:
    """通过向上查找 'packages' 目录来可靠地定位项目根目录。"""
    current = start_path.resolve()
    while not (current / 'packages').is_dir():
        if current.parent == current:
            raise FileNotFoundError("无法定位项目根目录 (未找到 'packages' 文件夹)。")
        current = current.parent
    return current

def build_file_tree(root_path: Path, dirs_to_scan: list[str], files_to_include: list[str]) -> list[Path]:
    """构建需要包含在快照中的所有文件的有序列表。"""
    all_files = []

    for file_path_str in files_to_include:
        path = root_path / file_path_str
        if path.is_file():
            all_files.append(path)

    for dir_str in dirs_to_scan:
        scan_path = root_path / dir_str
        if not scan_path.is_dir():
            continue
        
        for path in sorted(scan_path.glob('**/*')):
            if any(part in EXCLUDE_PATTERNS for part in path.parts) or path.name in EXCLUDE_PATTERNS:
                continue
            if path.is_file():
                all_files.append(path)
    
    return sorted(list(set(all_files)))


def write_snapshot(root_path: Path, file_list: list[Path], file: IO[str]):
    """将目录结构和文件内容写入输出文件。"""
    file.write("## 目录结构\n\n")
    tree = {}
    for path in file_list:
        relative_path = path.relative_to(root_path)
        parts = relative_path.parts
        current_level = tree
        for part in parts:
            current_level = current_level.setdefault(part, {})
    
    def write_tree(current_level: dict, indent: str = ""):
        for i, (name, subtree) in enumerate(sorted(current_level.items())):
            connector = "└── " if i == len(current_level) - 1 else "├── "
            file.write(f"{indent}{connector}{name}\n")
            if subtree:
                new_indent = indent + ("    " if i == len(current_level) - 1 else "│   ")
                write_tree(subtree, new_indent)
    
    write_tree(tree)
    file.write("\n")

    file.write("## 文件内容\n\n")
    for path in file_list:
        relative_path = path.relative_to(root_path)
        file.write(f"### `{relative_path}`\n\n")
        try:
            content = path.read_text("utf-8")
            lang = path.suffix.lstrip('.') if path.suffix else "text"
            if lang == 'py': lang = 'python'
            
            file.write(f"```{lang}\n")
            file.write(content.strip())
            file.write("\n```\n\n")
        except Exception as e:
            file.write(f"```text\n[无法读取文件内容: {e}]\n```\n\n")


def main():
    """脚本主入口。"""
    console = Console()
    
    parser = argparse.ArgumentParser(
        description="生成 Trans-Hub Monorepo 项目的完整快照。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-o", "--output", type=str, default="project_snapshot.txt",
        help="输出快照文件的名称（将保存在根目录下）。"
    )
    args = parser.parse_args()
    
    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        console.print(f"[bold red]错误: {e}[/bold red]")
        exit(1)

    output_path = project_root / args.output
    console.print(f"🚀 [bold cyan]正在生成项目快照...[/bold cyan]")
    console.print(f"   - [dim]项目根目录:[/dim] {project_root}")
    console.print(f"   - [dim]输出文件:[/dim] {output_path}")

    file_list = build_file_tree(project_root, DEFAULT_PACKAGES_DIRS, ROOT_FILES_TO_INCLUDE)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Trans-Hub Monorepo 项目快照 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
        write_snapshot(project_root, file_list, f)

    console.print(f"\n[bold green]✅ 快照已成功生成:[/bold green] {output_path}")


if __name__ == "__main__":
    main()