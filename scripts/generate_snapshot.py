#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trans-Hub Monorepo 项目快照生成工具（纯标准库版 v6.3）

改动要点：
- 扫描根与输出位置明确：
  * 扫描根：自动向上选择“最高祖先的仓库根”（优先含 packages/；其次 .git/；再次 pyproject.toml）
  * 输出文件：默认始终写到“脚本所在目录”（即 scripts/ 同目录），满足“生成放在同目录下”诉求
- 仍可自定义文件名：--output project_snapshot.txt
- 其他：目录树 + 文件内容（截断/跳过二进制），--extra/--no-content/--max-bytes；支持 --scan-root、--debug

用法：
  # 任意目录执行，快照会写到脚本同目录（scripts/）
  python3 scripts/generate_snapshot.py

  # 指定扫描根
  python3 scripts/generate_snapshot.py --scan-root /path/to/Trans-Hub

  # 只输出目录树
  python3 scripts/generate_snapshot.py --no-content

  # 额外包含路径（相对扫描根）
  python3 scripts/generate_snapshot.py --extra .github configs

退出码：0 成功；非 0 为错误
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Iterable

import structlog

logger = structlog.get_logger()

# -------- 可调参数 --------
DEFAULT_DIRS = ["packages", "scripts", "docs", "alembic", "migrations"]
DEFAULT_ROOT_FILES = [
    ".env.example",
    "pyproject.toml",
    "poetry.toml",
    "README.md",
    "alembic.ini",
    ".gitignore",
    "ruff.toml",
    ".flake8",
    ".editorconfig",
    "LICENSE",
]
EXCLUDE_NAMES = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".DS_Store",
    "Thumbs.db",
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    ".coverage",
    "htmlcov",
    "temp",
}
BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".so",
    ".dylib",
    ".dll",
    ".wasm",
    ".db",
}
LANG_MAP = {
    ".py": "python",
    ".toml": "toml",
    ".ini": "ini",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".sql": "sql",
    ".md": "markdown",
    ".sh": "bash",
    ".ps1": "powershell",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".css": "css",
    ".html": "html",
    ".env": "bash",
}


# -------- 根目录发现（优选最高祖先） --------
def looks_like_repo_root(path: Path) -> tuple[bool, bool, bool]:
    """返回 (has_packages, has_git, has_pyproject) 三元布尔。"""
    return (
        (path / "packages").is_dir(),
        (path / ".git").exists(),
        (path / "pyproject.toml").is_file(),
    )


def find_best_repo_root(start: Path, debug: bool = False) -> Path | None:
    """
    自 start 向上遍历到磁盘根，收集所有候选，最终按优先级取“最高”祖先：
      1) 含 packages/ 的目录（Monorepo 根，最高优先）
      2) 含 .git/ 的目录
      3) 含 pyproject.toml 的目录
    """
    cur = start.resolve()
    best_packages: Path | None = None
    best_git: Path | None = None
    best_py: Path | None = None
    chain: list[str] = []

    while True:
        has_packages, has_git, has_py = looks_like_repo_root(cur)
        if debug:
            chain.append(
                f"{cur}  [packages={has_packages}, git={has_git}, py={has_py}]"
            )
        if has_packages:
            best_packages = cur  # 越往上覆盖为“更高祖先”
        if has_git:
            best_git = cur
        if has_py:
            best_py = cur
        if cur.parent == cur:
            break
        cur = cur.parent

    if debug:
        print("🔍 根目录向上搜索链：")
        for line in chain:
            print(" -", line)

    return best_packages or best_git or best_py


# -------- 扫描与过滤 --------
def iter_targets(scan_root: Path, extra: list[str]) -> list[Path]:
    """生成扫描起点：默认目录 + 额外路径 + 默认根文件（相对扫描根）。"""
    targets: list[Path] = []
    for d in DEFAULT_DIRS:
        p = (scan_root / d).resolve()
        if p.exists():
            targets.append(p)
    for e in extra:
        p = (scan_root / e).resolve()
        if p.exists():
            targets.append(p)
        else:
            print(f"[提示] 忽略不存在的路径：{e}", file=sys.stderr)
    for f in DEFAULT_ROOT_FILES:
        p = (scan_root / f).resolve()
        if p.exists():
            targets.append(p)
    return sorted(set(targets))


def should_exclude(path: Path) -> bool:
    """名称级排除（命中任一父级亦排除）。"""
    if path.name in EXCLUDE_NAMES:
        return True
    return any(parent.name in EXCLUDE_NAMES for parent in path.parents)


def walk_files(scan_root: Path, targets: Iterable[Path]) -> list[Path]:
    """递归收集文件，相对 scan_root 返回。"""
    result: list[Path] = []
    for entry in targets:
        if should_exclude(entry):
            continue
        if entry.is_file():
            result.append(entry.relative_to(scan_root))
            continue
        if entry.is_dir():
            for p in sorted(entry.rglob("*")):
                if should_exclude(p):
                    continue
                if p.is_file():
                    result.append(p.relative_to(scan_root))
    return sorted(set(result))


# -------- 内容输出 --------
def detect_binary(path: Path) -> bool:
    """粗略二进制判断：后缀或首 4KB 含 NUL；异常保守为二进制。"""
    if path.suffix.lower() in BINARY_EXTS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(4096)
            if b"\\x00" in chunk:
                return True
            try:
                chunk.decode("utf-8")
            except UnicodeDecodeError:
                # 可能是其它编码文本，先不据此判二进制
                pass
    except OSError:
        return True
    return False


def code_lang_for(path: Path) -> str:
    return LANG_MAP.get(path.suffix.lower(), (path.suffix.lstrip(".") or "text"))


def write_dir_tree(scan_root: Path, files: list[Path], out: IO[str]) -> None:
    out.write("## 目录结构\n\n")
    tree: dict[str, dict] = {}
    for rel in files:
        node = tree
        for part in rel.parts:
            node = node.setdefault(part, {})

    def render(node: dict[str, dict], indent: str = "") -> None:
        items = sorted(node.items(), key=lambda kv: kv[0])
        for i, (name, sub) in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            out.write(f"{indent}{connector}{name}\n")
            if sub:
                render(sub, indent + ("    " if i == len(items) - 1 else "│   "))

    render(tree)
    out.write("\n")


def write_file_contents(
    scan_root: Path, files: list[Path], out: IO[str], max_bytes: int, no_content: bool
) -> None:
    out.write("## 文件内容\n\n")
    if no_content:
        out.write("_已根据 --no-content 跳过文件内容，仅展示目录结构。_\n")
        return
    for rel in files:
        abs_path = (scan_root / rel).resolve()
        out.write(f"### `{rel.as_posix()}`\n\n")
        if detect_binary(abs_path):
            out.write("```text\n[二进制或非 UTF-8 纯文本文件，已跳过内容]\n```\n\n")
            continue
        try:
            with open(abs_path, "rb") as f:
                data = f.read(max_bytes + 1)
            truncated = len(data) > max_bytes
            if truncated:
                data = data[:max_bytes]
            text = data.decode("utf-8", errors="replace").strip()
            out.write(f"```{code_lang_for(abs_path)}\n{text}\n```\n\n")
            if truncated:
                out.write(
                    f"> ⚠︎ 文件过大，已按 --max-bytes={max_bytes} 截断，仅展示前部内容。\n\n"
                )
        except Exception as e:
            out.write(f"```text\n[无法读取文件内容: {e}]\n```\n\n")


# -------- 入口 --------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_snapshot",
        description="生成 Trans-Hub 的项目快照（目录树 + 文件内容）。扫描根自动向上发现（优先 packages/）。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="project_snapshot.txt",
        help="输出文件名（写入到脚本所在目录）。",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=512 * 1024,
        help="单文件最大读取字节数（超过截断）。",
    )
    parser.add_argument(
        "--no-content", action="store_true", help="仅输出目录树，不写文件内容。"
    )
    parser.add_argument(
        "--extra", nargs="*", default=[], help="额外包含路径（相对扫描根）。"
    )
    parser.add_argument(
        "--scan-root",
        type=str,
        default="",
        help="手工指定扫描根；留空则自动从 CWD 向上查找。",
    )
    parser.add_argument("--debug", action="store_true", help="打印根目录判定过程。")
    args = parser.parse_args()

    # 1) 扫描根：自动向上找“最高祖先”
    cwd = Path.cwd().resolve()
    if args.scan_root:
        scan_root = Path(args.scan_root).resolve()
        if not scan_root.exists():
            print(f"错误：指定的扫描根不存在：{scan_root}", file=sys.stderr)
            sys.exit(2)
    else:
        found = find_best_repo_root(cwd, debug=args.debug)
        if not found:
            print(
                "错误：未能自动发现仓库根。\n"
                "请使用 --scan-root 指定含 packages/ 或 .git/ 或 pyproject.toml 的目录。",
                file=sys.stderr,
            )
            sys.exit(2)
        scan_root = found

    # 2) 输出位置：始终写到“脚本所在目录”
    script_dir = Path(__file__).resolve().parent
    output_path = script_dir / args.output

    # 在写入新内容之前，先删除或清空输出文件
    try:
        if output_path.exists():
            output_path.unlink()
            print(f"🔄 已删除旧文件: {output_path}")
    except OSError as e:
        print(f"⚠️ 无法删除旧文件 {output_path}: {e}", file=sys.stderr)
        # 尝试清空文件内容而不是删除
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("")
            print(f"🔄 已清空旧文件内容: {output_path}")
        except OSError as e2:
            print(f"❌ 无法清空旧文件 {output_path}: {e2}", file=sys.stderr)
            sys.exit(3)

    targets = iter_targets(scan_root, args.extra)
    files = walk_files(scan_root, targets)

    logger.info("🚀 开始生成项目快照")
    logger.info(
        "开始生成项目快照",
        扫描根目录=str(scan_root),
        脚本目录=str(script_dir),
        输出文件=output_path.name
    )
    logger.info(
        "扫描配置",
        包含起点=', '.join(p.as_posix() for p in targets) if targets else '(空)',
        文件总数=len(files),
        模式="仅目录树（--no-content）" if args.no_content else "完整内容",
        最大字节=args.max_bytes
    )

    with io.open(output_path, "w", encoding="utf-8", newline="\n") as out:
        out.write(
            f"# Trans-Hub Monorepo 项目快照（{datetime.now().strftime('%Y-%m-%d %H:%M')}）\n\n"
        )
        out.write(
            "> 说明：本文件由脚本自动生成，包含目录结构与核心文件内容（可能截断）。\n\n"
        )
        write_dir_tree(scan_root, files, out)
        write_file_contents(scan_root, files, out, args.max_bytes, args.no_content)

    logger.info("快照生成完成", 输出路径=str(output_path))


if __name__ == "__main__":
    main()
