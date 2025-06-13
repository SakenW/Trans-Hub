"""trans_hub/utils.py

本模块包含项目范围内的通用工具函数。
"""

import hashlib
import json
from typing import Any, Dict, Optional

from trans_hub.types import GLOBAL_CONTEXT_SENTINEL  # 导入新定义的常量


def get_context_hash(
    context: Optional[Dict[str, Any]],
) -> str:  # <-- 核心修改：返回类型改为 str
    """为一个上下文（context）字典生成一个确定性的、稳定的哈希值。

    哈希过程遵循以下规则：
    1. 如果上下文为 None 或空字典，则返回一个特殊的哨兵值 (GLOBAL_CONTEXT_SENTINEL)，
       表示无特定上下文。这解决了 SQLite UNIQUE 约束中 NULL 值被视为不同的问题。
    2. 将字典转换为 JSON 字符串。为了保证哈希的确定性，
       - 键（keys）会按字母顺序排序。
       - 字符串之间不包含不必要的空格。
    3. 使用 SHA256 算法计算该 JSON 字符串的哈希值。
    4. 返回十六进制格式的哈希摘要。

    Args:
    ----
        context: 一个可序列化为 JSON 的字典，代表翻译的上下文信息。

    Returns:
    -------
        如果提供了上下文，则返回一个字符串形式的 SHA256 哈希值；
        否则返回 GLOBAL_CONTEXT_SENTINEL。

    """
    if not context:
        return GLOBAL_CONTEXT_SENTINEL  # <-- 核心修改：返回哨兵值

    try:
        context_string = json.dumps(
            context,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        context_bytes = context_string.encode("utf-8")

        hasher = hashlib.sha256()
        hasher.update(context_bytes)

        return hasher.hexdigest()

    except TypeError as e:
        raise ValueError("Context contains non-serializable data.") from e
