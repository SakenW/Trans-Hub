# packages/server/tests/integration/worker/test_worker_flow.py
"""
对后台翻译 Worker 的核心流程进行端到端集成测试。
"""
import pytest
from sqlalchemy import select

from trans_hub.application.coordinator import Coordinator
from trans_hub.infrastructure.db._schema import ThTmLinks, ThTmUnits, ThTransRev
from trans_hub.infrastructure.engines.factory import create_engine_instance
from trans_hub.workers._translation_worker import run_once
from trans_hub_core.types import TranslationStatus
from tests.helpers.factories import create_request_data

pytestmark = pytest.mark.asyncio


async def test_worker_processes_draft_task_successfully(coordinator: Coordinator):
    """
    [修复] 测试 Worker 的 `run_once` 函数是否能成功处理一个 'draft' 状态的任务。

    修复逻辑:
    1. 在测试用例中显式创建和管理 `active_engine` 的生命周期。
    2. 将 `coordinator` 和 `active_engine` 作为依赖注入到 `run_once` 中。
    3. 这确保了所有数据库操作都发生在同一个 `pytest-asyncio` 管理的事件循环中，
       从而解决了 "different loop" 的错误。
    """
    # --- 1. 准备阶段：创建一个 'draft' 任务 ---
    coordinator.config.active_engine = "debug"
    req_data = create_request_data(target_langs=["de"])
    content_id = await coordinator.request_translation(**req_data)
    
    head_before = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de",
        variant_key="-",
    )
    assert head_before is not None
    assert head_before.current_status == TranslationStatus.DRAFT
    assert head_before.current_no == 0

    # --- 2. 执行阶段：正确创建并注入依赖 ---
    active_engine = create_engine_instance(coordinator.config, "debug")
    await active_engine.initialize()
    try:
        await run_once(coordinator, active_engine)
    finally:
        await active_engine.close()

    # --- 3. 断言阶段：验证处理结果 ---
    head_after = await coordinator.handler.get_head_by_id(head_before.id)
    assert head_after is not None
    assert head_after.current_status == TranslationStatus.REVIEWED
    assert head_after.current_no == 1
    assert head_after.current_rev_id != head_before.current_rev_id

    async with coordinator._sessionmaker() as session:
        new_rev_stmt = select(ThTransRev).where(ThTransRev.id == head_after.current_rev_id)
        new_rev = (await session.execute(new_rev_stmt)).scalar_one_or_none()

    assert new_rev is not None
    assert new_rev.revision_no == 1
    assert new_rev.status == TranslationStatus.REVIEWED
    expected_text = f"Translated({req_data['source_payload']['text']}) to de"
    assert new_rev.translated_payload_json["text"] == expected_text
    assert new_rev.engine_name == "debug"

    async with coordinator._sessionmaker() as session:
        tm_link_stmt = select(ThTmLinks).where(
            ThTmLinks.translation_rev_id == new_rev.id
        )
        tm_link = (await session.execute(tm_link_stmt)).scalar_one_or_none()
        assert tm_link is not None, "翻译记忆库链接未创建"

        tm_unit_stmt = select(ThTmUnits).where(ThTmUnits.id == tm_link.tm_id)
        tm_unit = (await session.execute(tm_unit_stmt)).scalar_one_or_none()
        assert tm_unit is not None, "翻译记忆库条目未创建"
        assert tm_unit.tgt_payload["text"] == expected_text
