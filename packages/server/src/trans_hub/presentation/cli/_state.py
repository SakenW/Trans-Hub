# packages/server/src/trans_hub/presentation/cli/_state.py
"""
定义了 CLI 应用中用于上下文传递的共享状态容器。
"""
from trans_hub.config import TransHubConfig


class CLISharedState:
    """用于在 Typer 上下文中传递共享对象的容器。"""

    def __init__(self, config: TransHubConfig):
        self.config = config