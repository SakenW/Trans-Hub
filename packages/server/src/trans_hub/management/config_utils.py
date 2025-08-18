# packages/server/src/trans_hub/management/config_utils.py
"""
配置相关的工具函数，特别是用于安全表示的函数。
"""

from __future__ import annotations
from typing import Union
from sqlalchemy.engine.url import URL, make_url


def mask_db_url(url: Union[str, URL]) -> str:
    """
    安全地脱敏一个数据库连接 URL，将其密码替换为 '***'。

    Args:
        url: 一个 SQLAlchemy URL 对象或 DSN 字符串。

    Returns:
        一个脱敏后的 DSN 字符串，适合在日志或控制台中显示。
    """
    try:
        url_obj = make_url(url)
        # 使用 render_as_string(hide_password=True) 是最健壮的方式
        return url_obj.render_as_string(hide_password=True)
    except Exception:
        # 如果 URL 格式不正确，返回一个安全的提示信息
        return "[无法解析的数据库 URL]"
