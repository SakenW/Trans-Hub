# trans_hub/utils.py
"""
本模块包含项目范围内的通用工具函数。

这些函数被设计为无状态的、纯粹的辅助工具，用于执行如哈希计算、格式校验等常见任务。
v3.1 修订：移除了易产生误导的 `get_database_url` 函数，并增强了语言代码校验。
v3.2 修订: 全面采用 langcodes 库进行语言代码校验。
"""

import hashlib
import json
import re
from typing import Any

from langcodes import Language
from langcodes.tag_parser import LanguageTagError

from trans_hub.core.types import GLOBAL_CONTEXT_SENTINEL

# 语言子标签应该由 2-3 个字母组成 (BCP 47)
# https://www.rfc-editor.org/rfc/rfc5646.html#section-2.2.1
LANGUAGE_SUBTAG_PATTERN = re.compile(r"^[a-zA-Z]{2,3}$")


def get_context_hash(context: dict[str, Any] | None) -> str:
    """
    为一个上下文（context）字典生成一个确定性的、稳定的 SHA-256 哈希值。

    哈希过程是稳定的，即对于逻辑上相同的字典，即使键的顺序不同，
    也会生成相同的哈希值。空上下文会返回一个固定的哨兵值。

    Args:
        context: 一个可被 JSON 序列化的字典，或 None。

    Returns:
        上下文的十六进制哈希字符串。

    Raises:
        ValueError: 如果 context 包含无法被 JSON 序列化的数据。

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
    使用 `langcodes` 库校验语言代码列表中的每个代码是否符合 BCP 47 规范
    且包含一个有效的、2-3个字母的语言子标签。

    如果任何一个代码格式无法被解析或不符合业务规则，则抛出 ValueError。

    Args:
        lang_codes: 一个包含语言代码字符串的列表。

    Raises:
        ValueError: 如果任何一个语言代码格式无效。

    """
    for code in lang_codes:
        try:
            lang = Language.get(code)
            if not lang.language:
                raise LanguageTagError(
                    f"The tag '{code}' is a valid BCP-47 tag, but does not contain a language subtag."
                )
            # 额外检查：语言子标签必须符合 2-3 个字母的规范
            if not LANGUAGE_SUBTAG_PATTERN.match(lang.language):
                raise LanguageTagError(
                    f"The language subtag '{lang.language}' in tag '{code}' does not conform to the expected format (2-3 alphabetic characters)."
                )
        except LanguageTagError as e:
            raise ValueError(f"提供的语言代码 '{code}' 格式无效。原因: {e}") from e
