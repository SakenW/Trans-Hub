# tests/helpers/lifecycle.py
# [v2.4.2 Final Architecture] 根除死锁/挂起问题。
# run_worker_until_idle 采用确定性的数据库状态检查和硬性超时。
"""
封装完整的端到端业务流程，使集成测试更简洁、更具可读性。
遵循白皮书 v2.4 的 rev/head 模型。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select

from trans_hub._uida.encoder import generate_uid_components
from trans_hub.core.types import TranslationStatus
from trans_hub.db.schema import ThTransHead

if TYPE_CHECKING:
    from trans_hub.coordinator import Coordinator
    from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class AppLifecycleManager:
    """一个管理 Trans-Hub 完整业务流程的测试助手。"""

    def __init__(self, coordinator: Coordinator):
        self.coordinator = coordinator
        self.handler: BasePersistenceHandler = coordinator.handler  # type: ignore[assignment]

    async def request_and_process(
        self, request_data: dict[str, Any]
    ) -> dict[str, ThTransHead]:
        """
        一个高级助手，它会模拟完整的端到端流程：
        1. 发起一个 UIDA 翻译请求。
        2. 模拟运行 Worker 处理所有新生成的 draft 任务。
        3. 返回所有目标语言的最终翻译头记录 (ThTransHead ORM 对象)。
        """
        await self.coordinator.request(**request_data)
        await self.run_worker_until_idle()

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
        """模拟 Worker 运行一次，处理所有可用的 'draft' 任务。"""
        from trans_hub.cli.worker import consume_and_process

        return await consume_and_process(self.coordinator, reason="test_lifecycle_run")

    async def run_worker_until_idle(self, timeout: float = 10.0) -> int:
        """[核心修正] 持续运行 Worker 直到数据库中没有草稿任务，并带有超时。"""
        total_processed = 0
        logger.bind(test_phase="run_worker_until_idle")

        async def _get_draft_count() -> int:
            # 类型转换：PersistenceHandler -> BasePersistenceHandler

            base_handler = self.handler
            async with base_handler._sessionmaker() as session:
                stmt = (
                    select(func.count())
                    .select_from(ThTransHead)
                    .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
                )
                result = await session.execute(stmt)
                return result.scalar_one() or 0

        async def wait_for_completion() -> None:
            iteration = 0
            while True:
                await asyncio.sleep(0.1)  # 添加小延迟避免CPU过度使用

                iteration += 1
                draft_count_before = await _get_draft_count()
                total_processed = 0
                logger.info(
                    "Worker 轮询开始",
                    iteration=iteration,
                    drafts_remaining=draft_count_before,
                )

                if draft_count_before == 0:
                    logger.info("没有剩余草稿，Worker 轮询结束。")
                    break

                processed = await self.run_worker_once()
                total_processed += processed
                logger.info(
                    "Worker 单次运行完毕",
                    processed_in_run=processed,
                    total_processed=total_processed,
                )

                # 在两次轮询之间短暂地让出控制权，以防万一
                await asyncio.sleep(0.1)

        try:
            await asyncio.wait_for(wait_for_completion(), timeout=timeout)
        except asyncio.TimeoutError:
            draft_count_after = await _get_draft_count()
            logger.error(
                "Worker 未能在规定时间内处理完所有任务，测试超时！",
                timeout=timeout,
                drafts_remaining=draft_count_after,
            )
            raise AssertionError(
                f"Worker processing timed out after {timeout}s. "
                f"{draft_count_after} draft tasks remain."
            ) from None

        return total_processed
