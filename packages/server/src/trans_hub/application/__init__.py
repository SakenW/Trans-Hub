# packages/server/src/trans_hub/application/__init__.py
"""
应用服务层。

本模块负责编排领域逻辑和基础设施，以完成具体的业务用例。
总协调器 (Coordinator) 是本层的核心，也是对外的唯一服务入口。
"""
from .coordinator import Coordinator

__all__ = ["Coordinator"]