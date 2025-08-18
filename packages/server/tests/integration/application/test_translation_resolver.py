# tests/integration/application/test_translation_resolver.py
"""
对 TranslationResolver 的核心回退逻辑进行集成测试 (最终修复版)。
"""

from __future__ import annotations
import uuid
import pytest

from tests.helpers.factories import create_request_data
from trans_hub.application.resolvers import TranslationResolver
from trans_hub.application.services import (
    RequestTranslationService,
    RevisionLifecycleService,
)
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.types import TranslationStatus
from trans_hub.config import TransHubConfig


@pytest.mark.asyncio
async def test_resolver_with_full_fallback_chain(
    uow_factory: UowFactory,
    test_config: TransHubConfig,
):
    """
    [核心验证] 验证 TranslationResolver 是否能正确地执行完整的变体和语言回退链。
    """
    # --- 1. 准备数据 ---
    project_id = f"fallback-proj-{uuid.uuid4().hex[:4]}"

    # 实例化准备数据所需的服务
    request_service = RequestTranslationService(uow_factory, test_config)
    lifecycle_service = RevisionLifecycleService(uow_factory, test_config)

    req_data = create_request_data(
        project_id=project_id, keys={"id": "fallback-test-ui"}, target_langs=[]
    )
    content_id = await request_service.execute(**req_data)

    async with uow_factory() as uow:
        (head_de_id, _) = await uow.translations.get_or_create_head(
            project_id, content_id, "de", "-"
        )
        rev_id_de = await uow.translations.create_revision(
            head_id=head_de_id,
            project_id=project_id,
            content_id=content_id,
            target_lang="de",
            variant_key="-",
            status=TranslationStatus.REVIEWED,
            revision_no=1,
            translated_payload_json={"text": "Hallo aus Deutschland"},
        )
    await lifecycle_service.publish(rev_id_de, "test-setup")

    async with uow_factory() as uow:
        await uow.misc.set_fallback_order(
            project_id=project_id, locale="de-CH", fallback_order=["de", "en"]
        )

    # --- 2. 执行 ---
    resolver = TranslationResolver(uow_factory)
    result_payload, resolved_rev_id = await resolver.resolve_with_fallback(
        project_id=project_id,
        content_id=content_id,
        target_lang="de-CH",
        variant_key="some-variant",
    )

    # --- 3. 验证 ---
    assert result_payload is not None
    assert result_payload.get("text") == "Hallo aus Deutschland"
    assert resolved_rev_id == rev_id_de
