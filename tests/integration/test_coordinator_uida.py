# tests/integration/test_coordinator_uida.py
"""
对白皮书 v1.2 Coordinator 进行端到端测试。
"""
import pytest
from sqlalchemy import select

from tests.helpers.factories import create_uida_request_data
from tests.helpers.lifecycle import AppLifecycleManager
from trans_hub.coordinator import Coordinator
from trans_hub.core import TranslationStatus
from trans_hub.db.schema import ThTranslations

pytestmark = pytest.mark.asyncio


@pytest.fixture
def lifecycle(coordinator: Coordinator) -> AppLifecycleManager:
    """提供一个与 Coordinator 绑定的生命周期管理器。"""
    return AppLifecycleManager(coordinator)


async def test_e2e_tm_miss_workflow(lifecycle: AppLifecycleManager):
    """
    [E2E v1.2] 测试 TM 未命中时的完整流程：
    - 请求后，创建 draft 任务。
    - Worker 处理后，任务状态变为 reviewed，获得翻译结果，并链接到新的 TM 条目。
    """
    # 1. 准备数据
    request_data = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_miss"},
        source_payload={"text": "Translate me"},
        target_langs=["de"],
    )

    # 2. 执行完整流程
    final_translations = await lifecycle.request_and_process(request_data)

    # 3. 断言最终状态
    assert "de" in final_translations
    de_translation = final_translations["de"]

    assert de_translation.status == TranslationStatus.REVIEWED.value
    assert de_translation.translated_payload_json is not None
    assert de_translation.translated_payload_json["text"] == "Translated(Translate me) to de"

    # 验证 TM 链接是否建立
    async with lifecycle.handler._sessionmaker() as session:
        from trans_hub.db.schema import ThTmLinks
        stmt = select(ThTmLinks).where(ThTmLinks.translation_id == de_translation.id)
        link = (await session.execute(stmt)).scalar_one_or_none()
        assert link is not None


async def test_e2e_tm_hit_workflow(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """
    [E2E v1.2] 测试 TM 命中时的流程：
    - 第一次请求，走 TM 未命中流程，创建 TM 条目。
    - 第二次请求（相同复用键），应直接命中 TM，创建 reviewed 任务，无需 Worker 介入。
    """
    # 1. 第一次请求，填充 TM
    request_data_1 = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_hit_1"},
        source_payload={"text": "Login"},
        target_langs=["fr"],
    )
    await lifecycle.request_and_process(request_data_1)

    # 2. 第二次请求，使用不同的 UIDA 但相同的复用键
    request_data_2 = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_hit_2"},
        source_payload={"text": "Login"},
        target_langs=["fr"],
    )
    
    # 只发起请求，不运行 Worker
    await coordinator.request(**request_data_2)

    # 3. 断言第二次请求的结果
    content_id_2 = await lifecycle.handler.upsert_content(
        project_id=request_data_2["project_id"],
        namespace=request_data_2["namespace"],
        keys=request_data_2["keys"],
        source_payload=request_data_2["source_payload"],
        content_version=request_data_2.get("content_version", 1),
    )
    async with lifecycle.handler._sessionmaker() as session:
        stmt = select(ThTranslations).where(
            ThTranslations.content_id == content_id_2,
            ThTranslations.target_lang == "fr",
        )
        translation_obj = (await session.execute(stmt)).scalar_one()

        # 状态应直接是 REVIEWED
        assert translation_obj.status == TranslationStatus.REVIEWED.value
        assert translation_obj.translated_payload_json is not None
        assert translation_obj.translated_payload_json["text"] == "Translated(Login) to fr"
        
        # 验证 TM 链接
        from trans_hub.db.schema import ThTmLinks
        link_stmt = select(ThTmLinks).where(ThTmLinks.translation_id == translation_obj.id)
        link = (await session.execute(link_stmt)).scalar_one_or_none()
        assert link is not None