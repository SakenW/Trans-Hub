# packages/server/src/trans_hub/presentation/cli/_shared_options.py
"""
CLI 共享参数定义库

本模块使用 typing.Annotated 和 Typer 为所有可复用的 CLI 选项
提供单一事实来源 (SSOT)。这确保了所有命令中相同参数的
帮助文本、短名称和行为完全一致。
"""
from __future__ import annotations

from typing import Annotated
import typer

# --- UIDA 相关选项 ---
PROJECT_ID_OPTION = Annotated[
    str, typer.Option("--project-id", "-p", help="项目/租户的唯一标识符。")
]

NAMESPACE_OPTION = Annotated[
    str, typer.Option("--namespace", "-n", help="内容的命名空间，如 'ui.buttons.v1'。")
]

KEYS_JSON_OPTION = Annotated[
    str, typer.Option("--keys", "-k", help="定位内容的最小上下文键集 (JSON 字符串)。")
]

# --- 通用选项 ---
ACTOR_OPTION = Annotated[
    str, typer.Option("--actor", help="操作者身份。", show_default="cli_user")
]