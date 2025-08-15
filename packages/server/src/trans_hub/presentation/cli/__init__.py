# packages/server/src/trans_hub/presentation/cli/__init__.py
"""
Trans-Hub Server CLI 的初始化模块。

此模块为了兼容旧的导入方式而存在，
建议直接使用 trans_hub.presentation.cli.main:app 作为入口点。
"""
from .main import app  # 导入主应用实例

# 保持向后兼容性
from .commands import db
