# trans_hub/utils.py
"""本模块包含项目范围内的通用工具函数。."""

import hashlib
import json
import re  # <--- 请务必确认这一行存在！
from typing import Any, Optional

from trans_hub.types import GLOBAL_CONTEXT_SENTINEL


def get_context_hash(context: Optional[dict[str, Any]]) -> str:
    """为一个上下文（context）字典生成一个确定性的、稳定的哈希值。."""
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
        raise ValueError("Context contains non-serializable data.") from e


def validate_lang_codes(lang_codes: list[str]) -> None:
    """
    校验语言代码列表中的每个代码是否符合 'en' 或 'zh-CN' 格式。
    如果任何一个代码无效，则抛出 ValueError。.
    """
    lang_code_pattern = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
    for code in lang_codes:
        if not lang_code_pattern.match(code):
            raise ValueError(f"提供的语言代码 '{code}' 格式无效。")
