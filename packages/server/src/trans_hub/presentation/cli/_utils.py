# packages/server/src/trans_hub/presentation/cli/_utils.py
"""
CLI 内部共享的辅助工具，例如用于管理 Coordinator 生命周期的上下文管理器。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

# [修复] 直接从 bootstrap 导入顶层工厂函数，并从 infrastructure.db 导入 dispose_engine
from trans_hub.bootstrap import create_coordinator
from trans_hub.infrastructure.db import dispose_engine
from trans_hub.application.coordinator import Coordinator
from ._state import CLISharedState


@asynccontextmanager
async def get_coordinator(state: CLISharedState) -> AsyncGenerator[Coordinator, None]:
    """
    一个异步上下文管理器，用于安全地初始化和关闭 Coordinator。
    它现在是 bootstrap.create_coordinator 的一个简单包装。
    """
    # [修复] 直接调用 bootstrap 中的 SSOT 工厂函数
    coordinator, db_engine = await create_coordinator(state.config)
    try:
        yield coordinator
    finally:
        await coordinator.close()
        if db_engine:
            await dispose_engine(db_engine)
