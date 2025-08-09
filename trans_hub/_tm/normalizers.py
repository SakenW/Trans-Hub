# trans_hub/_tm/normalizers.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from html import unescape
from typing import Any

# 预编译正则表达式以提高性能
RE_HTML_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*)?>")
RE_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
RE_URL = re.compile(
    r"\b(?:https?://|www\.)[a-zA-Z0-9\-\._~:/?#\[\]@!$&'()*+,;=%]+\b"
)
RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
RE_NUM = re.compile(r"\b\d+([.,]\d+)?\b")
RE_WHITESPACE = re.compile(r"\s+")


def normalize_plain_text_for_reuse(text: Any) -> str:
    """
    对纯文本进行归一化，以提高翻译记忆库 (TM) 的复用命中率。
    此函数是健壮的，可以处理非字符串输入。

    处理步骤:
    1. 确保输入是字符串。
    2. HTML 实体解码 (e.g., '&amp;' -> '&')。
    3. 移除 HTML 标签的属性，只保留标签名 (e.g., '<a href="..">' -> '<a>')。
    4. 将标准占位符 (e.g., '{name}') 替换为通用占位符 '{VAR}'。
    5. 将 UUID、URL 和数字替换为通用占位符 '{UUID}', '{URL}', '{NUM}'。
    6. 将连续的空白字符压缩为单个空格并移除首尾空白。

    Args:
        text: 待处理的文本，可以是任何类型。

    Returns:
        归一化后的字符串。
    """
    if not isinstance(text, str):
        return str(text)

    # 流程化处理，每一步都建立在前一步的基础上
    normalized_text = unescape(text)
    normalized_text = RE_HTML_TAG.sub(r"<\1>", normalized_text)
    normalized_text = RE_PLACEHOLDER.sub("{VAR}", normalized_text)
    normalized_text = RE_UUID.sub("{UUID}", normalized_text)
    normalized_text = RE_URL.sub("{URL}", normalized_text)
    normalized_text = RE_NUM.sub("{NUM}", normalized_text)
    normalized_text = RE_WHITESPACE.sub(" ", normalized_text).strip()

    return normalized_text