# trans_hub/cli/state.py
"""定义 CLI 应用的共享状态对象。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig


class State:
    """一个简单的类，用于通过 Typer 上下文传递共享状态。"""

    def __init__(self, config: "TransHubConfig") -> None:
        """初始化状态对象。

        Args:
            config: Trans-Hub 的主配置对象。
        """
        self.config = config
