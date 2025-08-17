# packages/server/tests/integration/workers/test_worker_run_once.py
"""
对后台翻译 Worker 的核心流程进行集成测试。
"""
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.helpers.factories import create_request_data
from tests.helpers.tools.fakes import FakeTranslationEngine, FakeEngineConfig
from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import ThTmLinks, ThTmUnits, ThTransRev, ThTransHead
from trans_hub.workers._translation_worker import run_once
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_worker_processes_draft_task_successfully(
    coordinator: Coordinator,
    db_sessionmaker: async_sessionmaker,
):
    """
    验证 Worker 的 `run_once` 函数能否成功处理一个 'draft' 任务，
    并正确地更新数据库状态（创建新修订、TM等）。
    """
    # 1. 准备：创建一个 'draft' 状态的翻译任务
    req_data = create_request_data(target_langs=["de"], keys={"id": f"worker-test-{uuid.uuid4().hex[:4]}"})
    await coordinator.request_translation(**req_data)
    
    uida_params = {
        "project_id": req_data["project_id"],
        "namespace": req_data["namespace"],
        "keys": req_data["keys"],
        "target_lang": "de",
        "variant_key": "-",
    }
    head_before = await coordinator.handler.get_translation_head_by_uida(**uida_params)
    
    assert head_before is not None
    assert head_before.current_status == TranslationStatus.DRAFT
    assert head_before.current_no == 0

    # 2. 执行：调用 worker 的核心处理逻辑
    fake_engine = FakeTranslationEngine(config=FakeEngineConfig())
    await run_once(coordinator, fake_engine)

    # 3. 验证：检查数据库的最终状态
    async with db_sessionmaker() as session:
        head_after = (await session.execute(
            select(ThTransHead).where(ThTransHead.id == head_before.id)
        )).scalar_one()
        
        assert head_after.current_status == TranslationStatus.REVIEWED
        assert head_after.current_no == 1
        assert head_after.current_rev_id != head_before.current_rev_id

        new_rev = (await session.execute(
            select(ThTransRev).where(ThTransRev.id == head_after.current_rev_id)
        )).scalar_one()
        
        expected_text = f"Translated('{req_data['source_payload']['text']}') to de"
        assert new_rev.translated_payload_json["text"] == expected_text
        
        # [最终修复] 使用正确的期望值 'faketranslation'
        assert new_rev.engine_name == "faketranslation"
        assert new_rev.status == TranslationStatus.REVIEWED

        tm_link = (await session.execute(
            select(ThTmLinks).where(ThTmLinks.translation_rev_id == new_rev.id)
        )).scalar_one_or_none()
        assert tm_link is not None, "翻译记忆库链接未创建"

        tm_unit = (await session.execute(
            select(ThTmUnits).where(ThTmUnits.id == tm_link.tm_id)
        )).scalar_one_or_none()
        assert tm_unit is not None, "翻译记忆库条目未创建"
        assert tm_unit.tgt_payload["text"] == expected_text