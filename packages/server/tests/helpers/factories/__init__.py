# packages/server/tests/helpers/factories/__init__.py
"""
Factories __init__ file - Exposes all factory functions for easy importing.
"""
from .request_factory import create_request_data

# 当你添加 content_factory.py 和 tm_factory.py 时，也在这里导出它们
# from .content_factory import ...
# from .tm_factory import ...

__all__ = ["create_request_data"]