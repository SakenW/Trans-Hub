# tests/integration/test_persistence_uida.py
# [v2.4] 持久化层集成测试
"""
对白皮书 v2.4 持久化层的集成测试。
直接与数据库交互，验证核心数据操作的正确性。
"""
from __future__ import annotations

import pytest

from tests.helpers.factories import TEST_NAMESPACE, TEST_PROJECT_ID
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import TranslationStatus
from trans_hub.db.schema import ThTransHead, ThTransRev

pytestmark = pytest.mark.asyncio


async def test_upsert_content_is_idempotent(handler: PersistenceHandler):
    """测试 `upsert_content` 的幂等性。"""
    keys = {"view": "home", "id": "title"}
    
    content_id_1 = await handler.upsert_content(
        TEST_PROJECT_ID, TEST_NAMESPACE, keys, {"text": "Welcome"}, 1
    )
    content_id_2 = await handler.upsert_content(
        TEST_PROJECT_ID, TEST_NAMESPACE, keys, {"text": "Welcome v2"}, 2 # 内容更新
    )
    
    assert content_id_1 == content_id_2, "对于相同的 UIDA，content_id 必须相同"


async def test_rev_head_creation_and_update(handler: PersistenceHandler):
    """测试翻译的 rev/head 记录能否被正确创建和更新。"""
    content_id = await handler.upsert_content(
        TEST_PROJECT_ID, TEST_NAMESPACE, {"id": "rev-head-test"}, {"text": "Test"}, 1
    )

    # 1. 首次为该维度请求，应创建 head 和 rev 0
    head_id, rev_no = await handler.get_or_create_translation_head(
        TEST_PROJECT_ID, content_id, "de", "-"
    )
    assert head_id is not None
    assert rev_no == 0

    # 2. 创建一个新的 'reviewed' 修订
    rev_id_1 = await handler.create_new_translation_revision(
        head_id=head_id, project_id=TEST_PROJECT_ID, content_id=content_id,
        target_lang="de", variant_key="-", status=TranslationStatus.REVIEWED,
        revision_no=rev_no + 1, translated_payload={"text": "Testen"}
    )
    
    # 3. 验证 head 已更新
    async with handler._sessionmaker() as session:
        head = (await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))).scalar_one()
        assert head.current_rev_id == rev_id_1
        assert head.current_no == 1
        assert head.current_status == TranslationStatus.REVIEWED.value
        assert head.published_rev_id is None # 尚未发布

    # 4. 发布该修订
    success = await handler.publish_revision(rev_id_1)
    assert success is True

    # 5. 验证 head 的发布指针已更新
    async with handler._sessionmaker() as session:
        head = (await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))).scalar_one()
        rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == rev_id_1))).scalar_one()
        assert head.published_rev_id == rev_id_1
        assert head.published_no == 1
        assert rev.status == TranslationStatus.PUBLISHED.value