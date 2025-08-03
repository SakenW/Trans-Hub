# trans_hub/cli/utils.py
"""提供 CLI 命令使用的共享工具函数。"""

import structlog
from rich.console import Console

from trans_hub.config import TransHubConfig
from trans_hub.coordinator import Coordinator
from trans_hub.persistence.sqlite import SQLitePersistenceHandler

logger = structlog.get_logger(__name__)
console = Console()


def create_coordinator(config: TransHubConfig) -> Coordinator:
    """
    根据配置创建并返回一个 Coordinator 实例。

    v3.1 修复：此函数现在是创建 Coordinator 的唯一入口，
    确保了创建逻辑的一致性。

    Args:
        config: Trans-Hub 的主配置对象。

    Returns:
        一个未初始化的 Coordinator 实例。
    """
    handler = SQLitePersistenceHandler(config.database_url)
    return Coordinator(config, handler)
