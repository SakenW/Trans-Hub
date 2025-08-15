# packages/server/src/trans_hub/presentation/cli/_utils.py
"""
CLI 内部共享的辅助工具，例如用于管理 Coordinator 生命周期的上下文管理器。
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from trans_hub.application.coordinator import Coordinator
from ._state import CLISharedState  # [REFACTOR] 从新的 state 模块导入


@asynccontextmanager
async def get_coordinator(state: CLISharedState) -> AsyncGenerator[Coordinator, None]:
    """
    一个异步上下文管理器，用于安全地初始化和关闭 Coordinator。
    这是 CLI 中所有与应用层交互的命令的推荐模式。
    """
    coordinator = Coordinator(state.config)
    try:
        await coordinator.initialize()
        yield coordinator
    finally:
        await coordinator.close()