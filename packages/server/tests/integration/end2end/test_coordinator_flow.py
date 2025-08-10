# packages/server/tests/integration/end2end/test_coordinator_flow.py
"""
对 Coordinator 进行端到端的核心业务流程测试。
"""
import pytest

from trans_hub.application.coordinator import Coordinator
from tests.helpers.factories import create_request_data

pytestmark = pytest.mark.asyncio

async def test_full_request_publish_get_flow(coordinator: Coordinator):
    """测试从请求 -> (模拟处理) -> 发布 -> 获取的完整快乐路径。"""
    req_data = create_request_data(target_langs=["de"])
    
    # 1. 提交请求，TM 未命中，应创建 DRAFT
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(**req_data)
    assert head is not None and head.current_status == "draft"

    # 2. 模拟 Worker 处理：直接创建一个新的 'reviewed' 修订
    rev_id = await coordinator.handler.create_new_translation_revision(
        head_id=head.id, project_id=head.project_id, content_id=head.content_id,
        target_lang=head.target_lang, variant_key=head.variant_key,
        status="reviewed", revision_no=head.current_no + 1,
        translated_payload_json={"text": "Hallo Welt"}
    )
    
    # 3. 发布
    success = await coordinator.publish_translation(rev_id)
    assert success is True

    # 4. 获取
    result = await coordinator.get_translation(**req_data, target_lang="de")
    assert result is not None
    assert result["text"] == "Hallo Welt"

async def test_commenting_flow(coordinator: Coordinator):
    """测试添加和获取评论的端到端流程。"""
    req_data = create_request_data()
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(**req_data)
    assert head is not None

    # 添加评论
    comment_body = "This translation needs more context."
    comment_id = await coordinator.add_comment(head.id, "reviewer-1", comment_body)
    assert isinstance(comment_id, str)
    
    # 获取评论
    comments = await coordinator.get_comments(head.id)
    assert len(comments) == 1
    assert comments[0].body == comment_body
    assert comments[0].author == "reviewer-1"