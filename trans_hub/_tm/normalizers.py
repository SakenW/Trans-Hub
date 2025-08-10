# trans_hub/_tm/normalizers.py
# [v1.1 Final] 修正正则表达式，正确处理闭合 HTML 标签和带逗号的数字。
from __future__ import annotations

import re
from html import unescape
from typing import Any

# [核心修正] 分别处理开启和闭合标签
RE_HTML_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
RE_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
RE_URL = re.compile(r"\b(?:https?://|www\.)[a-zA-Z0-9\-\._~:/?#\[\]@!$&'()*+,;=%]+\b")
RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# [核心修正] 匹配包含逗号和多个小数点的数字
RE_NUM = re.compile(r"\b\d[\d,.]*\b")
RE_WHITESPACE = re.compile(r"\s+")


def normalize_plain_text_for_reuse(text: Any) -> str:
    """对纯文本进行归一化，以提高翻译记忆库 (TM) 的复用命中率。"""
    if not isinstance(text, str):
        return str(text)

    normalized_text = unescape(text)

    # [核心修正] 使用一个函数来正确处理标签的闭合
    def _strip_tag_attributes(match: re.Match[str]) -> str:
        tag = match.group(0)
        tag_name = match.group(1)
        if tag.startswith("</"):
            return f"</{tag_name}>"
        else:
            return f"<{tag_name}>"

    normalized_text = RE_HTML_TAG.sub(_strip_tag_attributes, normalized_text)
    normalized_text = RE_PLACEHOLDER.sub("{VAR}", normalized_text)
    normalized_text = RE_UUID.sub("{UUID}", normalized_text)
    normalized_text = RE_URL.sub("{URL}", normalized_text)
    normalized_text = RE_NUM.sub("{NUM}", normalized_text)
    normalized_text = RE_WHITESPACE.sub(" ", normalized_text).strip()

    return normalized_text
