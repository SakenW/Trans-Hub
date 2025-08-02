# trans_hub/utils.py
"""
本模块包含项目范围内的通用工具函数。

这些函数被设计为无状态的、纯粹的辅助工具，用于执行如哈希计算、格式校验等常见任务。
"""

import hashlib
import json
import re
from typing import Any, Optional

from trans_hub.config import TransHubConfig
from trans_hub.types import GLOBAL_CONTEXT_SENTINEL


def get_context_hash(context: Optional[dict[str, Any]]) -> str:
    """
    为一个上下文（context）字典生成一个确定性的、稳定的 SHA-256 哈希值。

    哈希过程是稳定的，即对于逻辑上相同的字典，即使键的顺序不同，
    也会生成相同的哈希值。空上下文会返回一个固定的哨兵值。

    参数:
        context: 一个可被 JSON 序列化的字典，或 None。

    返回:
        上下文的十六进制哈希字符串。
    """
    if not context:
        return GLOBAL_CONTEXT_SENTINEL

    try:
        context_string = json.dumps(
            context, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        context_bytes = context_string.encode("utf-8")
        hasher = hashlib.sha256()
        hasher.update(context_bytes)
        return hasher.hexdigest()
    except TypeError as e:
        raise ValueError("Context 包含无法被 JSON 序列化的数据。") from e


def validate_lang_codes(lang_codes: list[str]) -> None:
    """
    校验语言代码列表中的每个代码是否符合 BCP 47 的常见格式 (例如 'en', 'zh-CN')。

    如果任何一个代码格式无效，则抛出 ValueError。

    参数:
        lang_codes: 一个包含语言代码字符串的列表。
    """
    lang_code_pattern = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
    for code in lang_codes:
        if not lang_code_pattern.match(code):
            raise ValueError(f"提供的语言代码 '{code}' 格式无效。")


def get_database_url() -> str:
    """
    从配置中获取数据库 URL。

    返回:
        数据库 URL 字符串。
    """
    config = TransHubConfig()
    return config.database_url
