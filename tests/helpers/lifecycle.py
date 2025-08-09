# tests/helpers/lifecycle.py
"""
封装完整的端到端业务流程，使集成测试更简洁、更具可读性。
遵循白皮书 Final v1.2。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from trans_hub.db.schema import ThTranslations

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
    ) -> dict[str, Any]:
        """
        一个高级助手，它会模拟完整的端到端流程：
        1. 发起一个 UIDA 翻译请求。
        2. 模拟运行 Worker 处理所有新生成的 draft 任务。
        3. 返回所有目标语言的最终翻译记录 (ORM 对象)。
        """
        # 1. 发起请求
        await self.coordinator.request(**request_data)

        # 2. 模拟 Worker 运行
        await self.run_worker_until_idle()

        # 3. 获取并返回结果
        content_id = await self.handler.upsert_content(
            project_id=request_data["project_id"],
            namespace=request_data["namespace"],
            keys=request_data["keys"],
            source_payload=request_data["source_payload"],
            content_version=request_data.get("content_version", 1),
        )

        final_translations = {}
        async with self.handler._sessionmaker() as session:
            for lang in request_data["target_langs"]:
                stmt = select(ThTranslations).where(
                    ThTranslations.content_id == content_id,
                    ThTranslations.target_lang == lang,
                )
                result = await session.execute(stmt)
                translation_obj = result.scalar_one_or_none()
                if translation_obj:
                    final_translations[lang] = translation_obj

        return final_translations

    async def run_worker_once(self) -> int:
        """
        [v1.2] 模拟 Worker 运行一次，处理所有可用的 'draft' 任务。
        此方法现在直接调用 coordinator 中的 consume_and_process 逻辑。
        """
        # 为了测试，我们直接借用 CLI worker 中的核心处理函数
        from trans_hub.cli.worker import consume_and_process

        return await consume_and_process(self.coordinator, reason="test_lifecycle_run")

    async def run_worker_until_idle(self) -> int:
        """持续运行 Worker 直到没有更多可处理的任务。"""
        total_processed = 0
        while True:
            processed = await self.run_worker_once()
            if processed == 0:
                break
            total_processed += processed
        return total_processed