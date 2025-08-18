# tests/integration/application/test_translation_resolver.py
"""
对 TranslationResolver 的核心回退逻辑进行集成测试 (UoW 重构版)。
"""

from __future__ import annotations

import uuid
import pytest

from tests.helpers.factories import create_request_data
from trans_hub.application.coordinator import Coordinator
from trans_hub_core.types import TranslationStatus


pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_resolver_with_full_fallback_chain(
    coordinator: Coordinator,
):
    """
    [核心验证] 验证 TranslationResolver 是否能正确地执行完整的变体和语言回退链。
    场景: 请求 de-CH -> 未找到 -> 回退到 de (默认变体) -> 找到并返回。
    """
    # --- 1. 准备数据 ---
    project_id = f"fallback-proj-{uuid.uuid4().hex[:4]}"

    # 1a. 提交一个内容
    req_data = create_request_data(
        project_id=project_id,
        keys={"id": "fallback-test-ui"},
        target_langs=[],  # 初始不创建任何翻译
    )
    content_id = await coordinator.request_translation(**req_data)

    # 1b. 为回退目标 de (德语) 创建一个已发布的翻译
    async with coordinator._uow_factory() as uow:
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
    await coordinator.publish_translation(rev_id_de)

    # 1c. 在数据库中设置回退规则: de-CH -> de
    async with coordinator._uow_factory() as uow:
        await uow.misc.set_fallback_order(
            project_id=project_id, locale="de-CH", fallback_order=["de", "en"]
        )

    # --- 2. 执行 ---
    # 直接使用 coordinator 内部的 resolver 实例进行测试
    resolver = coordinator.resolver
    result_payload, resolved_rev_id = await resolver.resolve_with_fallback(
        project_id=project_id,
        content_id=content_id,
        target_lang="de-CH",
        variant_key="some-variant",  # 故意使用一个不存在的变体
    )

    # --- 3. 验证 ---
    assert result_payload is not None, "解析器应该成功回退并找到一个结果"
    assert (
        result_payload.get("text") == "Hallo aus Deutschland"
    ), "应该返回德语的回退翻译"
    assert resolved_rev_id == rev_id_de, "应该返回德语修订版的 ID"
