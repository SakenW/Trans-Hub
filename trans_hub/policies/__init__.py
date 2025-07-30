# trans_hub/policies/__init__.py
"""本模块作为处理策略的公共入口，导出核心策略类和接口。"""

from .processing import DefaultProcessingPolicy, ProcessingPolicy

__all__ = [
    "DefaultProcessingPolicy",
    "ProcessingPolicy",
]
