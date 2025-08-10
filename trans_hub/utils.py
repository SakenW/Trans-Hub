# trans_hub/utils.py
"""
本模块包含项目范围内的通用工具函数。
v3.2 修订: 全面采用 langcodes 库进行语言代码校验。
"""

import re

from langcodes import Language
from langcodes.tag_parser import LanguageTagError

# 语言子标签应该由 2-3 个字母组成 (BCP 47)
LANGUAGE_SUBTAG_PATTERN = re.compile(r"^[a-zA-Z]{2,3}$")


def validate_lang_codes(lang_codes: list[str]) -> None:
    """使用 `langcodes` 库校验语言代码列表中的每个代码是否符合 BCP 47 规范。"""
    for code in lang_codes:
        try:
            lang = Language.get(code)
            if not lang.language or not LANGUAGE_SUBTAG_PATTERN.match(lang.language):
                raise LanguageTagError(
                    f"Tag '{code}' lacks a valid 2-3 letter language subtag."
                )
        except LanguageTagError as e:
            raise ValueError(f"提供的语言代码 '{code}' 格式无效。原因: {e}") from e
