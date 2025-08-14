# src/trans_hub/domain/tm.py
"""
包含与翻译记忆库 (TM) 相关的核心领域逻辑。
"""

from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from typing import Any

# 预编译正则表达式以提高性能
RE_HTML_TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")
RE_PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
RE_URL = re.compile(r"\b(?:https?://|www\.)[a-zA-Z0-9\-\._~:/?#\[\]@!$&'()*+,;=%]+\b")
RE_UUID = re.compile(r"\b[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
RE_NUM = re.compile(r"\b\d[\d,.]*\b")
RE_WHITESPACE = re.compile(r"\s+")


def normalize_text_for_tm(text: Any) -> str:
    """
    对纯文本进行归一化，以提高翻译记忆库 (TM) 的复用命中率。

    归一化流程：
    1. HTML 反转义 (e.g., `&amp;` -> `&`)。
    2. 移除 HTML 标签的属性。
    3. 将具名占位符 (e.g., `{user_name}`) 替换为通用占位符 (`{VAR}`)。
    4. 将 UUID、URL、数字等替换为通用类别占位符。
    5. 将连续的空白字符压缩为单个空格。

    Args:
        text: 待处理的输入文本。

    Returns:
        归一化后的文本字符串。
    """
    if not isinstance(text, str):
        return str(text)

    normalized = unescape(text)

    def _strip_tag_attributes(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        return f"</{tag_name}>" if match.group(0).startswith("</") else f"<{tag_name}>"

    normalized = RE_HTML_TAG.sub(_strip_tag_attributes, normalized)
    normalized = RE_PLACEHOLDER.sub("{VAR}", normalized)
    normalized = RE_UUID.sub("{UUID}", normalized)
    normalized = RE_URL.sub("{URL}", normalized)
    normalized = RE_NUM.sub("{NUM}", normalized)
    normalized = RE_WHITESPACE.sub(" ", normalized).strip()

    return normalized


def build_reuse_key(
    *,
    namespace: str,
    reduced_keys: dict[str, Any],
    source_fields: dict[str, Any],
) -> bytes:
    r"""
    构建用于在翻译记忆库 (TM) 中查找的复用键（SHA-256哈希）。

    复用键的计算公式为：
    `SHA256( namespace + '\n' + JCS(reduced_keys) + '\n' + JCS(source_fields) )`

    Args:
        namespace: 内容的命名空间。
        reduced_keys: 经过策略降维后的 keys。
        source_fields: 从源 payload 中提取的、经过归一化的、参与复用判定的字段。

    Returns:
        32字节的 SHA-256 哈希摘要字节串。
    """
    try:
        keys_json = json.dumps(
            reduced_keys, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        source_json = json.dumps(
            source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except TypeError as e:
        raise ValueError(f"无法序列化用于复用键的字典: {e}") from e

    blob = f"{namespace}\n{keys_json}\n{source_json}".encode("utf-8")
    return hashlib.sha256(blob).digest()
