# packages/server/tests/integration/persistence/test_persistence.py
"""
对持久化层 (PersistenceHandler) 的核心方法进行集成测试。
"""
import pytest

from tests.helpers.factories import create_request_data
from trans_hub.application.coordinator import Coordinator # Easiest way to get a configured handler
from trans_hub_core.interfaces import PersistenceHandler
from trans_hub_core.types import Comment, TranslationStatus

pytestmark = pytest.mark.asyncio

@pytest.fixture
def handler(coordinator: Coordinator) -> PersistenceHandler:
    """从 coordinator fixture 中提取 handler。"""
    return coordinator.handler

async def test_upsert_content_is_idempotent(handler: PersistenceHandler):
    """测试 `upsert_content` 的幂等性。"""
    req = create_request_data()
    
    content_id_1 = await handler.upsert_content(
        project_id=req["project_id"], namespace=req["namespace"], keys=req["keys"],
        source_payload=req["source_payload"], content_version=1
    )
    content_id_2 = await handler.upsert_content(
        project_id=req["project_id"], namespace=req["namespace"], keys=req["keys"],
        source_payload={"text": "Updated text"}, content_version=2
    )
    assert content_id_1 == content_id_2

async def test_full_revision_lifecycle(handler: PersistenceHandler):
    """测试从创建 Head -> 新增修订 -> 发布 -> 拒绝的完整流程。"""
    req = create_request_data()
    content_id = await handler.upsert_content(**req) # Simplified call
    
    head_id, rev_no = await handler.get_or_create_translation_head(
        req["project_id"], content_id, "de", "-"
    )
    assert rev_no == 0

    # 创建 'reviewed' 修订
    rev1_id = await handler.create_new_translation_revision(
        head_id=head_id, project_id=req["project_id"], content_id=content_id,
        target_lang="de", variant_key="-", status=TranslationStatus.REVIEWED, revision_no=1
    )
    head = await handler.get_head_by_id(head_id)
    assert head.current_rev_id == rev1_id and head.current_status == "reviewed"

    # 发布修订
    success = await handler.publish_revision(rev1_id)
    assert success
    head_after_publish = await handler.get_head_by_id(head_id)
    assert head_after_publish.published_rev_id == rev1_id
    
    # 拒绝修订 (虽然已发布，但业务上可能允许，此处仅测试 DB 操作)
    success_reject = await handler.reject_revision(rev1_id)
    assert success_reject