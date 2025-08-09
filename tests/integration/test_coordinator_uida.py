# tests/integration/test_coordinator_uida.py
# [v1.7 - 终极版测试逻辑]
"""
对白皮书 v1.2 Coordinator 进行端到端测试。
"""
import pytest
from sqlalchemy import select

from tests.helpers.factories import create_uida_request_data
from tests.helpers.lifecycle import AppLifecycleManager
from trans_hub._uida.encoder import generate_uid_components
from trans_hub.coordinator import Coordinator
from trans_hub.core import TranslationStatus
from trans_hub.db.schema import ThLocalesFallbacks, ThTranslations

pytestmark = pytest.mark.asyncio


@pytest.fixture
def lifecycle(coordinator: Coordinator) -> AppLifecycleManager:
    """提供一个与 Coordinator 绑定的生命周期管理器。"""
    return AppLifecycleManager(coordinator)


async def test_e2e_tm_miss_workflow(lifecycle: AppLifecycleManager):
    """
    [E2E v1.2] 测试 TM 未命中时的完整流程。
    """
    request_data = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_miss"},
        source_payload={"text": "Translate me"},
        target_langs=["de"],
    )
    final_translations = await lifecycle.request_and_process(request_data)
    assert "de" in final_translations
    de_translation = final_translations["de"]
    assert de_translation.status == TranslationStatus.REVIEWED.value
    assert de_translation.translated_payload_json["text"] == "Translated(Translate me) to de"
    async with lifecycle.handler._sessionmaker() as session:
        from trans_hub.db.schema import ThTmLinks
        stmt = select(ThTmLinks).where(ThTmLinks.translation_id == de_translation.id)
        link = (await session.execute(stmt)).scalar_one_or_none()
        assert link is not None


async def test_e2e_tm_hit_workflow(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """
    [E2E v1.2] 测试 TM 命中时的流程。
    """
    request_data_1 = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_hit_1"},
        source_payload={"text": "Login"},
        target_langs=["fr"],
    )
    await lifecycle.request_and_process(request_data_1)
    request_data_2 = create_uida_request_data(
        keys={"view": "e2e", "id": "tm_hit_2"},
        source_payload={"text": "Login"},
        target_langs=["fr"],
    )
    await coordinator.request(**request_data_2)
    _, _, keys_sha = generate_uid_components(request_data_2["keys"])
    content_id_2 = await lifecycle.handler.get_content_id_by_uida(
        project_id=request_data_2["project_id"],
        namespace=request_data_2["namespace"],
        keys_sha256_bytes=keys_sha,
    )
    async with lifecycle.handler._sessionmaker() as session:
        stmt = select(ThTranslations).where(
            ThTranslations.content_id == content_id_2,
            ThTranslations.target_lang == "fr",
        )
        translation_obj = (await session.execute(stmt)).scalar_one()
        assert translation_obj.status == TranslationStatus.REVIEWED.value
        assert translation_obj.translated_payload_json["text"] == "Translated(Login) to fr"
        from trans_hub.db.schema import ThTmLinks
        link_stmt = select(ThTmLinks).where(ThTmLinks.translation_id == translation_obj.id)
        link = (await session.execute(link_stmt)).scalar_one_or_none()
        assert link is not None


async def test_publish_and_reject_workflow(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """[新增] 测试发布和拒绝的工作流。"""
    # [v1.7 修正] 使用固定的 source_payload 以进行确定性断言
    fixed_source_payload = {"text": "Publish Me"}
    request_data = create_uida_request_data(
        target_langs=["es"], source_payload=fixed_source_payload
    )
    final_translations = await lifecycle.request_and_process(request_data)
    translation_id = final_translations["es"].id

    publish_success = await coordinator.publish_translation(translation_id)
    assert publish_success is True

    get_params = {
        "project_id": request_data["project_id"],
        "namespace": request_data["namespace"],
        "keys": request_data["keys"],
        "target_lang": request_data["target_langs"][0],
        "variant_key": request_data["variant_key"],
    }
    result = await coordinator.get_translation(**get_params)
    assert result is not None
    assert "Translated(Publish Me) to es" == result["text"]

    reject_success = await coordinator.reject_translation(translation_id)
    assert reject_success is True
    async with lifecycle.handler._sessionmaker() as session:
        stmt = select(ThTranslations.status).where(ThTranslations.id == translation_id)
        status = (await session.execute(stmt)).scalar_one()
        assert status == TranslationStatus.REJECTED.value


async def test_get_translation_with_fallback(
    coordinator: Coordinator, lifecycle: AppLifecycleManager
):
    """[v1.7 终极修正] 测试 get_translation 的语言和变体回退逻辑。"""
    # [v1.7 核心修正] 手动构造数据，确保 keys 字典完全一致
    project_id = "prj_fallback"
    namespace = "test.ui.buttons.v1"
    shared_keys = {"id": "fallback_test", "view": "profile"}
    source_payload = {"text": "Fallback"}

    # 1. 创建并发布用于回退的翻译记录
    # 1.1 创建并发布 zh-Hant 的默认变体
    hant_default_req = {
        "project_id": project_id, "namespace": namespace, "keys": shared_keys,
        "source_payload": source_payload, "target_langs": ["zh-Hant"], "variant_key": "-",
        "source_lang": "en"
    }
    processed_hant = await lifecycle.request_and_process(hant_default_req)
    await coordinator.publish_translation(processed_hant["zh-Hant"].id)

    # 1.2 创建并发布 zh-Hans 的默认变体
    hans_default_req = {
        "project_id": project_id, "namespace": namespace, "keys": shared_keys,
        "source_payload": source_payload, "target_langs": ["zh-Hans"], "variant_key": "-",
        "source_lang": "en"
    }
    processed_hans = await lifecycle.request_and_process(hans_default_req)
    await coordinator.publish_translation(processed_hans["zh-Hans"].id)

    # 2. 创建一个 "formal" 变体的草稿，但不发布它
    hant_formal_req = {
        "project_id": project_id, "namespace": namespace, "keys": shared_keys,
        "source_payload": source_payload, "target_langs": ["zh-Hant"], "variant_key": "formal",
        "source_lang": "en"
    }
    await lifecycle.request_and_process(hant_formal_req)

    # 3. 设置回退策略
    async with lifecycle.handler._sessionmaker() as session:
        fallback_rule = ThLocalesFallbacks(
            project_id=project_id,
            locale="zh-HK",
            fallback_order=["zh-Hant", "zh-Hans"],
        )
        session.add(fallback_rule)
        await session.commit()

    # 4. 开始测试回退
    # 4.1 测试变体回退：查询 zh-Hant formal (未发布), 应回退到已发布的 zh-Hant default
    result_variant_fallback = await coordinator.get_translation(
        project_id=project_id, namespace=namespace,
        keys=shared_keys, target_lang="zh-Hant", variant_key="formal"
    )
    assert result_variant_fallback is not None
    assert "Translated(Fallback) to zh-Hant" == result_variant_fallback["text"]

    # 4.2 测试语言回退：查询一个不存在的语言 zh-HK，应按顺序回退到已发布的 zh-Hant
    result_lang_fallback = await coordinator.get_translation(
        project_id=project_id, namespace=namespace,
        keys=shared_keys, target_lang="zh-HK", variant_key="-"
    )
    assert result_lang_fallback is not None
    assert "Translated(Fallback) to zh-Hant" == result_lang_fallback["text"]