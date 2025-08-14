# packages/server/tests/integration/end2end/test_coordinator_flow.py
"""
对 Coordinator 进行端到端的核心业务流程测试。(v2.5.14 对齐版)
"""

import pytest
from trans_hub.application.coordinator import Coordinator
from trans_hub_core.types import TranslationStatus
from tests.helpers.factories import create_request_data

pytestmark = pytest.mark.asyncio


async def test_full_request_publish_get_flow(coordinator: Coordinator):
    """测试从请求 -> (模拟处理) -> 发布 -> 获取的完整快乐路径。"""
    req_data = create_request_data(target_langs=["de"])

    await coordinator.request_translation(**req_data)

    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de",
        variant_key="-",
    )
    assert head is not None
    assert head.current_status == TranslationStatus.DRAFT

    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id,
        project_id=head.project_id,
        content_id=head.content_id,
        target_lang=head.target_lang,
        variant_key=head.variant_key,
        status=TranslationStatus.REVIEWED,
        revision_no=head.current_no + 1,
        translated_payload_json={"text": "Hallo Welt"},
    )
    assert rev_id is not None

    success = await coordinator.publish_translation(rev_id)
    assert success is True

    result = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de",
    )
    assert result is not None
    assert result["text"] == "Hallo Welt"


async def test_language_fallback_flow(coordinator: Coordinator):
    """[新增] 测试语言回退链是否按预期工作。"""
    # 1. 准备数据：一个英语原文，并发布一个德语译文
    req_data = create_request_data(target_langs=["de"], keys={"id": "fallback_test"})
    content_id = await coordinator.request_translation(**req_data)
    head_de = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de",
        variant_key="-",
    )
    rev_id_de = await coordinator.handler.create_new_translation_revision(
        head_id=head_de.id,
        project_id=req_data["project_id"],
        content_id=content_id,
        target_lang="de",
        variant_key="-",
        status=TranslationStatus.REVIEWED,
        revision_no=head_de.current_no + 1,
        translated_payload_json={"text": "Hallo aus Deutschland"},
    )
    await coordinator.publish_translation(rev_id_de)

    # 2. 设置回退链：请求瑞士德语(de-CH)时，应先找 de-CH，再找 de
    await coordinator.handler.set_fallback_order(
        project_id=req_data["project_id"],
        locale="de-CH",
        fallback_order=["de"],
    )

    # 3. 验证回退
    # 第一次请求 de-CH，由于 de-CH 不存在，应回退到 de
    result = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="de-CH",
    )
    assert result is not None
    assert result["text"] == "Hallo aus Deutschland"

    # 4. 验证无回退的情况
    # 请求一个没有配置回退链的语言，应该返回 None
    result_fr = await coordinator.get_translation(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang="fr",
    )
    assert result_fr is None


async def test_commenting_flow(coordinator: Coordinator):
    """测试添加和获取评论的端到端流程。"""
    req_data = create_request_data()
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(
        project_id=req_data["project_id"],
        namespace=req_data["namespace"],
        keys=req_data["keys"],
        target_lang=req_data["target_langs"][0],
        variant_key="-",
    )
    assert head is not None

    comment_body = "这条翻译需要更多上下文。"
    comment_id = await coordinator.add_comment(head.id, "reviewer-1", comment_body)
    assert isinstance(comment_id, str)

    comments = await coordinator.get_comments(head.id)
    assert len(comments) == 1
    assert comments[0].body == comment_body
    assert comments[0].author == "reviewer-1"
