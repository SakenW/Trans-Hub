# tests/integration/test_coordinator_uida.py
# [v2.4] Coordinator 端到端集成测试
"""
对白皮书 v2.4 Coordinator 进行端到端测试。
使用 AppLifecycleManager 模拟完整的业务流程。
"""
import pytest
from sqlalchemy import select

from tests.helpers.factories import create_uida_request_data
from tests.helpers.lifecycle import AppLifecycleManager
from trans_hub.coordinator import Coordinator
from trans_hub.core import TranslationStatus
from trans_hub.db.schema import ThLocalesFallbacks, ThTmLinks, ThTransRev

pytestmark = pytest.mark.asyncio


@pytest.fixture
def lifecycle(coordinator: Coordinator) -> AppLifecycleManager:
    """提供一个与 Coordinator 绑定的生命周期管理器。"""
    return AppLifecycleManager(coordinator)


async def test_e2e_tm_miss_workflow(lifecycle: AppLifecycleManager):
    """测试 TM 未命中时的完整流程：request -> draft -> reviewed。"""
    request_data = create_uida_request_data(target_langs=["de"])
    
    final_heads = await lifecycle.request_and_process(request_data)
    
    assert "de" in final_heads
    head = final_heads["de"]
    assert head.current_status == TranslationStatus.REVIEWED.value
    
    # 验证修订记录和 TM 链接
    async with lifecycle.handler._sessionmaker() as session:
        rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == head.current_rev_id))).scalar_one()
        assert rev.translated_payload_json["text"] == f"Translated({request_data['source_payload']['text']}) to de"
        
        link = (await session.execute(select(ThTmLinks).where(ThTmLinks.translation_rev_id == rev.id))).scalar_one_or_none()
        assert link is not None, "TM 未命中后，应创建新的 TM 条目和链接"


async def test_e2e_tm_hit_workflow(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """测试 TM 命中时的流程：request -> reviewed。"""
    # 1. 第一次请求，TM 未命中，填充 TM
    shared_payload = {"text": "Login"}
    request_data_1 = create_uida_request_data(source_payload=shared_payload, target_langs=["fr"])
    await lifecycle.request_and_process(request_data_1)

    # 2. 第二次请求，具有相同的可复用内容，应命中 TM
    request_data_2 = create_uida_request_data(source_payload=shared_payload, target_langs=["fr"])
    
    # 只请求，不处理，因为 TM 命中应该同步完成
    await coordinator.request(**request_data_2)
    
    # 3. 直接验证结果
    final_heads = await lifecycle.request_and_process(request_data_2) # Worker should do nothing
    head = final_heads["fr"]
    assert head.current_status == TranslationStatus.REVIEWED.value, "TM 命中应直接创建 reviewed 状态的修订"
    async with lifecycle.handler._sessionmaker() as session:
        rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == head.current_rev_id))).scalar_one()
        assert rev.translated_payload_json["text"] == "Translated(Login) to fr"


async def test_publish_and_get_translation_workflow(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """测试发布和获取已发布翻译的完整流程。"""
    request_data = create_uida_request_data(target_langs=["es"])
    final_heads = await lifecycle.request_and_process(request_data)
    head = final_heads["es"]
    
    # 发布 'reviewed' 状态的修订
    success = await coordinator.publish_translation(head.current_rev_id)
    assert success is True
    
    # 现在通过 get_translation 应该能获取到结果
    get_params = {
        "project_id": request_data["project_id"],
        "namespace": request_data["namespace"],
        "keys": request_data["keys"],
        "target_lang": "es",
        "variant_key": request_data["variant_key"],
    }
    result = await coordinator.get_translation(**get_params)
    assert result is not None
    assert result["text"] == f"Translated({request_data['source_payload']['text']}) to es"

    # 获取一个不存在的语言，应返回 None
    result_none = await coordinator.get_translation(target_lang="it", **get_params)
    assert result_none is None


async def test_get_translation_with_fallback(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """测试 get_translation 的语言回退逻辑。"""
    shared_keys = {"id": "fallback_test"}
    # 1. 创建并发布一个 'en' -> 'de' 的翻译
    req_de = create_uida_request_data(keys=shared_keys, target_langs=["de"])
    heads_de = await lifecycle.request_and_process(req_de)
    await coordinator.publish_translation(heads_de["de"].current_rev_id)

    # 2. 设置 'fr' -> 'de' 的回退策略
    async with lifecycle.handler._sessionmaker() as session:
        fallback_rule = ThLocalesFallbacks(
            project_id=TEST_PROJECT_ID, locale="fr", fallback_order=["de", "en"]
        )
        session.add(fallback_rule)
        await session.commit()

    # 3. 请求 'fr' 的翻译，但不要发布它
    req_fr = create_uida_request_data(keys=shared_keys, target_langs=["fr"])
    await lifecycle.request_and_process(req_fr)
    
    # 4. 现在获取 'fr' 的翻译，由于它未发布，应回退到已发布的 'de'
    get_params = {
        "project_id": TEST_PROJECT_ID,
        "namespace": TEST_NAMESPACE,
        "keys": shared_keys,
        "target_lang": "fr",
    }
    result = await coordinator.get_translation(**get_params)
    assert result is not None
    assert result["text"] == f"Translated({req_de['source_payload']['text']}) to de"