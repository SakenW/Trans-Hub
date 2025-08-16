# packages/server/src/trans_hub/management/utils.py
"""
管理平面共享工具模块

本模块包含所有被管理工具（如 CLI、示例脚本、运维任务）复用的非核心业务逻辑。
"""

from __future__ import annotations

from pathlib import Path


def find_alembic_ini() -> Path:
    """
    自当前文件位置开始，自下而上查找并返回 alembic.ini 的绝对路径。
    这是一个健壮的查找器，适用于在 monorepo 中的任何位置执行脚本。
    """
    # 以此文件所在目录为起点
    start_dir = Path(__file__).resolve().parent

    # 向上遍历父目录，直到文件系统根目录
    for p in [start_dir, *start_dir.parents]:
        # 优先检查 monorepo 结构下的 packages/server/alembic.ini
        monorepo_path = p / "packages" / "server" / "alembic.ini"
        if monorepo_path.is_file():
            return monorepo_path

        # 其次检查当前目录或父目录是否直接包含 alembic.ini
        direct_path = p / "alembic.ini"
        if direct_path.is_file():
            return direct_path

    raise FileNotFoundError("无法在任何父目录中找到 Alembic 配置文件 'alembic.ini'。")
