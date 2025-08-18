# packages/server/src/trans_hub/presentation/cli/_utils.py
"""
CLI 内部共享的辅助工具，例如用于管理 Coordinator 生命周期的上下文管理器。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from trans_hub.application.coordinator import Coordinator
from trans_hub.bootstrap import create_uow_factory
from trans_hub.infrastructure.db import dispose_engine
from ._state import CLISharedState


@asynccontextmanager
async def get_coordinator(state: CLISharedState) -> AsyncGenerator[Coordinator, None]:
    """
    一个异步上下文管理器，用于安全地初始化和关闭 Coordinator。
    这是 CLI 中所有与应用层交互的命令的推荐模式。
    """
    # [修复] 使用 bootstrap 中的 UoW 工厂来正确创建 Coordinator
    uow_factory, db_engine = create_uow_factory(state.config)

    # [TODO] 理想情况下，Redis 客户端也应在这里注入
    # 为了简化，暂时假设 CLI 操作不直接依赖 Redis

    coordinator = Coordinator(config=state.config, uow_factory=uow_factory)
    try:
        await coordinator.initialize()
        yield coordinator
    finally:
        await coordinator.close()
        await dispose_engine(db_engine)  # 确保引擎被关闭
