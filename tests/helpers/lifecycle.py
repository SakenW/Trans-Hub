# tests/helpers/lifecycle.py
# [v2.4.1 Refactor] 修正 __future__ 导入拼写错误。
"""
封装完整的端到端业务流程，使集成测试更简洁、更具可读性。
遵循白皮书 v2.4 的 rev/head 模型。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from trans_hub._uida.encoder import generate_uid_components
from trans_hub.db.schema import ThTransHead

if TYPE_CHECKING:
    from trans_hub.coordinator import Coordinator
    from trans_hub.persistence.base import BasePersistenceHandler


class AppLifecycleManager:
    """一个管理 Trans-Hub 完整业务流程的测试助手。"""

    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator
        self.handler: BasePersistenceHandler = coordinator.handler

    async def request_and_process(
        self, request_data: dict[str, Any]
    ) -> dict[str, ThTransHead]:
        """
        一个高级助手，它会模拟完整的端到端流程：
        1. 发起一个 UIDA 翻译请求。
        2. 模拟运行 Worker 处理所有新生成的 draft 任务。
        3. 返回所有目标语言的最终翻译头记录 (ThTransHead ORM 对象)。
        """
        # 1. 发起请求
        await self.coordinator.request(**request_data)

        # 2. 模拟 Worker 运行，处理所有待办任务
        await self.run_worker_until_idle()

        # 3. 从数据库获取并返回最终的头记录
        _, _, keys_sha = generate_uid_components(request_data["keys"])
        content_id = await self.handler.get_content_id_by_uida(
            project_id=request_data["project_id"],
            namespace=request_data["namespace"],
            keys_sha256_bytes=keys_sha,
        )
        if not content_id:
            return {}

        final_heads = {}
        async with self.handler._sessionmaker() as session:
            for lang in request_data.get("target_langs", []):
                variant_key = request_data.get("variant_key", "-")
                stmt = select(ThTransHead).where(
                    ThTransHead.content_id == content_id,
                    ThTransHead.target_lang == lang,
                    ThTransHead.variant_key == variant_key,
                )
                result = await session.execute(stmt)
                head_obj = result.scalar_one_or_none()
                if head_obj:
                    final_heads[lang] = head_obj

        return final_heads

    async def run_worker_once(self) -> int:
        """
        模拟 Worker 运行一次，处理所有可用的 'draft' 任务。
        通过直接调用 CLI worker 的核心函数，确保测试与真实行为一致。
        """
        from trans_hub.cli.worker import consume_and_process

        return await consume_and_process(self.coordinator, reason="test_lifecycle_run")

    async def run_worker_until_idle(self) -> int:
        """持续运行 Worker 直到没有更多可处理的任务。"""
        total_processed = 0
        while True:
            # 在一个循环中重复运行 Worker，直到它报告没有处理任何任务
            processed = await self.run_worker_once()
            if processed == 0:
                break
            total_processed += processed
            # 添加一个微小的延迟，以允许事件循环处理其他可能排队的任务
            await asyncio.sleep(0.01)
        return total_processed