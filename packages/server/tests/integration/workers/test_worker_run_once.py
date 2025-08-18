# tests/integration/workers/test_worker_run_once.py
"""
对后台翻译 Worker 的核心流程进行集成测试 (UoW 重构版)。
"""

import uuid
import pytest

from tests.helpers.factories import create_request_data
from tests.helpers.tools.fakes import FakeTranslationEngine, FakeEngineConfig
from trans_hub.application.coordinator import Coordinator
from trans_hub.application.processors import TranslationProcessor
from trans_hub.infrastructure.uow import UowFactory
from trans_hub.workers._translation_worker import run_once
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_worker_processes_draft_task_successfully(
    coordinator: Coordinator,  # 用于方便地创建初始请求
    uow_factory: UowFactory,
):
    """
    验证 Worker 的 `run_once` 函数能否成功处理一个 'draft' 任务，
    并正确地更新数据库状态（创建新修订、TM等）。
    """
    # 1. 准备：使用 coordinator 创建一个 'draft' 状态的翻译任务
    req_data = create_request_data(
        target_langs=["de"], keys={"id": f"worker-test-{uuid.uuid4().hex[:4]}"}
    )
    await coordinator.request_translation(**req_data)

    # 验证初始状态
    async with uow_factory() as uow:
        head_before = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="de",
            variant_key="-",
        )
        assert head_before is not None
        assert head_before.current_status == TranslationStatus.DRAFT
        assert head_before.current_no == 0

    # 2. 准备 Worker 的依赖
    fake_engine = FakeTranslationEngine(config=FakeEngineConfig())
    # stream_producer 暂时为 None，因为事件现在走 Outbox
    processor = TranslationProcessor(stream_producer=None, event_stream_name="")

    # 3. 执行：调用 worker 的核心处理逻辑
    await run_once(
        uow_factory=uow_factory,
        processor=processor,
        active_engine=fake_engine,
        batch_size=10,
    )

    # 4. 验证：在新的 UoW 中检查数据库的最终状态
    async with uow_factory() as uow:
        head_after = await uow.translations.get_head_by_uida(
            project_id=req_data["project_id"],
            namespace=req_data["namespace"],
            keys=req_data["keys"],
            target_lang="de",
            variant_key="-",
        )

        assert head_after is not None
        assert head_after.current_status == TranslationStatus.REVIEWED
        assert head_after.current_no == 1
        assert head_after.current_rev_id != head_before.current_rev_id

        new_rev = await uow.translations.get_revision_by_id(head_after.current_rev_id)
        assert new_rev is not None

        expected_text = f"Translated('{req_data['source_payload']['text']}') to de"
        assert new_rev.translated_payload_json["text"] == expected_text

        assert new_rev.engine_name == "faketranslation"
        assert new_rev.status == TranslationStatus.REVIEWED

        link_exists = await uow.tm.check_link_exists(new_rev.id)
        assert link_exists is True, "翻译记忆库链接未创建"
