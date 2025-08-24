# packages/server/src/trans_hub/application/services/_event_publisher.py
"""
提供一个统一的、可注入的事件发布服务。
"""

import uuid
from typing import TYPE_CHECKING

from trans_hub_core.types import Event
from trans_hub_core.uow import IUnitOfWork

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig


class EventPublisher:
    """负责将领域事件通过 UoW 的发件箱进行发布的通用服务。"""

    def __init__(self, config: "TransHubConfig"):
        self._config = config

    async def publish(self, uow: IUnitOfWork, event: Event) -> None:
        """
        在一个给定的工作单元 (UoW) 上下文中发布一个事件。

        Args:
            uow: 当前的 Unit of Work 实例。
            event: 要发布的事件对象。
        """
        await uow.outbox.add(
            project_id=event.project_id,
            event_id=str(uuid.uuid4()),  # 每次发布都生成新的唯一事件ID
            topic=self._config.worker.event_stream_name,
            payload=event.model_dump(mode="json"),
        )
