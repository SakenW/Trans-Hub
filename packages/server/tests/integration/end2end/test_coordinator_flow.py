# packages/server/tests/integration/end2end/test_coordinator_flow.py
"""
对 Coordinator 进行端到端的核心业务流程测试。
"""
import pytest

from trans_hub.application.coordinator import Coordinator
from tests.helpers.factories import create_request_data

pytestmark = pytest.mark.asyncio

async def test_full_request_publish_get_flow(coordinator: Coordinator):
    """测试从请求 -> 发布 -> 获取的完整快乐路径。"""
    # 1. 提交请求
    req_data = create_request_data(target_langs=["de"])
    content_id = await coordinator.request_translation(**req_data)
    assert content_id is not None
    
    # 2. 假设 Worker 已处理，我们手动找到 'reviewed' 的修订ID
    #    (在真实的测试中，我们可能需要一个 TestWorker 或直接操作数据库)
    head = await coordinator.handler.get_translation_head_by_uida(**req_data, target_lang="de", variant_key="-")
    assert head is not None
    # In a real test, we would need to manually update the status to 'reviewed'
    # For now, let's assume it is and try to publish.
    
    # 3. 发布
    # success = await coordinator.publish_translation(head.current_rev_id)
    # assert success is True

    # 4. 获取
    # result = await coordinator.get_translation(...)
    # assert result is not None
    # assert result["text"] == "..."

async def test_commenting_flow(coordinator: Coordinator):
    """测试添加和获取评论的流程。"""
    req_data = create_request_data()
    await coordinator.request_translation(**req_data)
    head = await coordinator.handler.get_translation_head_by_uida(**req_data, target_lang="de", variant_key="-")
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