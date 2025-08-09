# tests/helpers/lifecycle.py
# [v1.4 - 修正缺失的导入]
"""
封装完整的端到端业务流程，使集成测试更简洁、更具可读性。
遵循白皮书 Final v1.2。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

# [v1.4 核心修正] 添加缺失的导入语句
from trans_hub._uida.encoder import generate_uid_components
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
        _, _, keys_sha = generate_uid_components(request_data["keys"])
        content_id = await self.handler.get_content_id_by_uida(
            project_id=request_data["project_id"],
            namespace=request_data["namespace"],
            keys_sha256_bytes=keys_sha,
        )

        final_translations = {}
        async with self.handler._sessionmaker() as session:
            for lang in request_data["target_langs"]:
                variant_key = request_data.get("variant_key", "-")
                stmt = select(ThTranslations).where(
                    ThTranslations.content_id == content_id,
                    ThTranslations.target_lang == lang,
                    ThTranslations.variant_key == variant_key,
                )
                result = await session.execute(stmt)
                translation_obj = result.scalar_one_or_none()
                if translation_obj:
                    final_translations[lang] = translation_obj

        return final_translations

    async def run_worker_once(self) -> int:
        """
        [v1.2] 模拟 Worker 运行一次，处理所有可用的 'draft' 任务。
        """
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