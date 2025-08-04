# trans_hub/persistence/utils.py
"""提供持久化层实现共享的通用工具函数。"""

import uuid


def generate_uuid() -> str:
    """生成一个标准的 UUID 字符串。"""
    return str(uuid.uuid4())
