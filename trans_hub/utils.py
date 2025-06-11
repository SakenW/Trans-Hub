"""
trans_hub/utils.py

本模块包含项目范围内的通用工具函数。
"""
import hashlib
import json
from typing import Any, Dict, Optional

def get_context_hash(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    为一个上下文（context）字典生成一个确定性的、稳定的哈希值。

    哈希过程遵循以下规则：
    1. 如果上下文为 None 或空字典，则返回 None，表示无特定上下文。
    2. 将字典转换为 JSON 字符串。为了保证哈希的确定性，
       - 键（keys）会按字母顺序排序。
       - 字符串之间不包含不必要的空格。
    3. 使用 SHA256 算法计算该 JSON 字符串的哈希值。
    4. 返回十六进制格式的哈希摘要。

    Args:
        context: 一个可序列化为 JSON 的字典，代表翻译的上下文信息。

    Returns:
        如果提供了上下文，则返回一个字符串形式的 SHA256 哈希值；
        否则返回 None。
    """
    if not context:
        return None

    try:
        # sort_keys=True 是保证哈希确定性的关键
        # separators=(',', ':') 则移除了多余的空格，进一步保证稳定性
        context_string = json.dumps(
            context,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False  # 允许非ASCII字符，以支持多语言内容
        )
        
        # 将字符串编码为 UTF-8 字节流进行哈希
        context_bytes = context_string.encode('utf-8')
        
        # 计算 SHA256 哈希
        hasher = hashlib.sha256()
        hasher.update(context_bytes)
        
        return hasher.hexdigest()

    except TypeError:
        # 如果 context 包含无法序列化为 JSON 的类型，则抛出异常
        # 这是契约违规，应该在调用此函数之前由 Pydantic 模型等进行校验
        raise ValueError("Context contains non-serializable data.")