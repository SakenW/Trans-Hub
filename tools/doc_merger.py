#!/usr/bin/env python3
# tools/doc_merger.py

import os
import sys
from pathlib import Path

"""
文档合并工具

功能:
1. 导出docs目录的结构
2. 合并所有.rst文件到一个txt文件中
"""

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class DocMerger:
    def __init__(self, docs_dir: str, output_file: str):
        self.docs_dir = Path(docs_dir)
        self.output_file = Path(output_file)
        self.separator = "\n" + "=" * 80 + "\n"

    def generate_directory_structure(self) -> str:
        """生成docs目录的结构"""
        structure = []
        structure.append(f"目录结构: {self.docs_dir}\n")

        # 需要排除的目录
        exclude_dirs = [".mypy_cache", "_static", "_build"]

        # 特殊处理根目录
        root_dir_name = os.path.basename(str(self.docs_dir)) + "/"
        structure.append(f"├── {root_dir_name}\n")

        for root, dirs, files in os.walk(self.docs_dir):
            # 过滤掉需要排除的目录
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            # 跳过根目录，因为已经单独处理
            if root == str(self.docs_dir):
                level = 1
                for dir_name in dirs:
                    structure.append(f"    ├── {dir_name}/\n")
                for file in files:
                    structure.append(f"    ├── {file}\n")
                continue

            level = root.replace(str(self.docs_dir), "").count(os.sep) + 1
            indent = " " * 4 * (level)
            folder_name = os.path.basename(root) + "/"
            structure.append(f"{indent}├── {folder_name}\n")

            subindent = " " * 4 * (level + 1)
            for file in files:
                structure.append(f"{subindent}├── {file}\n")

        return "".join(structure)

    def merge_rst_files(self) -> str:
        """合并所有.rst文件的内容"""
        merged_content = []

        # 查找所有.rst文件
        rst_files = list(self.docs_dir.rglob("*.rst"))
        rst_files.sort()  # 按文件名排序

        for file_path in rst_files:
            relative_path = file_path.relative_to(self.docs_dir)
            merged_content.append(f"文件: {relative_path}\n")

            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()
                    merged_content.append(content)
            except Exception as e:
                merged_content.append(f"读取文件错误: {str(e)}\n")

            merged_content.append(self.separator)

        return "".join(merged_content)

    def run(self) -> None:
        """运行工具"""
        # 生成目录结构
        dir_structure = self.generate_directory_structure()

        # 合并rst文件
        merged_rst = self.merge_rst_files()

        # 写入输出文件
        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(dir_structure)
            f.write(self.separator)
            f.write(merged_rst)

        print(f"成功导出文档结构和合并内容到: {self.output_file}")


if __name__ == "__main__":
    # 定义docs目录和输出文件路径
    project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    docs_dir = project_root / "docs"
    output_file = Path(__file__).parent / "docs_merged.txt"

    # 创建并运行DocMerger
    merger = DocMerger(str(docs_dir), str(output_file))
    merger.run()
