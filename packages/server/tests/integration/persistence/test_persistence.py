# packages/server/tests/integration/persistence/test_persistence.py
"""
对持久化层 (PersistenceHandler) 的核心方法进行集成测试。(v2.5.14 对齐版)
"""

import pytest
from datetime import datetime
from sqlalchemy import select

from tests.helpers.factories import create_request_data
from trans_hub.application.coordinator import Coordinator
from trans_hub_core.interfaces import PersistenceHandler
from trans_hub_core.types import TranslationStatus
from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThTransHead,
    ThTransRev,
    ThResolveCache,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def handler(coordinator: Coordinator) -> PersistenceHandler:
    """从 coordinator fixture 中提取 handler。"""
    return coordinator.handler


async def test_upsert_content_is_idempotent(
    handler: PersistenceHandler, coordinator: Coordinator
):
    """测试 `upsert_content` 的幂等性。"""
    req = create_request_data()

    content_id_1 = await handler.upsert_content(
        project_id=req["project_id"],
        namespace=req["namespace"],
        keys=req["keys"],
        source_payload=req["source_payload"],
        source_lang=req["source_lang"],
        content_version=1,
    )

    content_id_2 = await handler.upsert_content(
        project_id=req["project_id"],
        namespace=req["namespace"],
        keys=req["keys"],
        source_payload={"text": "更新后的文本"},
        source_lang=req["source_lang"],
        content_version=2,
    )

    assert content_id_1 == content_id_2

    # 使用handler的sessionmaker而非coordinator的，避免事件循环不匹配
    async with handler._sessionmaker() as session:
        result = await session.get(ThContent, content_id_1)
        assert result is not None
        assert result.source_payload_json["text"] == "更新后的文本"


async def test_full_revision_lifecycle(handler: PersistenceHandler):
    """测试从创建 Head -> 新增修订 -> 发布 -> 拒绝的完整流程。"""
    req = create_request_data()
    content_id = await handler.upsert_content(
        project_id=req["project_id"],
        namespace=req["namespace"],
        keys=req["keys"],
        source_payload=req["source_payload"],
        source_lang=req["source_lang"],
        content_version=1,
    )

    head_id, rev_no = await handler.get_or_create_translation_head(
        project_id=req["project_id"],
        content_id=content_id,
        target_lang="de",
        variant_key="-",
    )
    assert rev_no == 0

    rev1_id = await handler.create_new_translation_revision(
        head_id=head_id,
        project_id=req["project_id"],
        content_id=content_id,
        target_lang="de",
        variant_key="-",
        status=TranslationStatus.REVIEWED,
        revision_no=1,
    )
    head = await handler.get_head_by_id(head_id)
    assert head is not None and head.current_rev_id == rev1_id

    success = await handler.publish_revision(rev1_id)
    assert success
    head_after_publish = await handler.get_head_by_id(head_id)
    assert (
        head_after_publish is not None
        and head_after_publish.published_rev_id == rev1_id
    )

    success_reject = await handler.reject_revision(rev1_id)
    assert success_reject
    head_after_reject = await handler.get_head_by_id(head_id)
    assert (
        head_after_reject is not None
        and head_after_reject.current_status == TranslationStatus.REJECTED
    )


async def test_cascade_delete_from_content(
    handler: PersistenceHandler, coordinator: Coordinator
):
    """[新增] 验证删除 content 记录会级联删除所有关联的 rev, head 和 cache 记录。"""
    req = create_request_data(keys={"id": "cascade_delete_test"})
    # 过滤掉 upsert_content 方法不接受的参数
    filtered_req = {k: v for k, v in req.items() if k in ['project_id', 'namespace', 'keys', 'source_payload', 'source_lang']}
    content_id = await handler.upsert_content(**filtered_req, content_version=1)

    head_id, _ = await handler.get_or_create_translation_head(
        project_id=req["project_id"],
        content_id=content_id,
        target_lang="de",
        variant_key="-",
    )

    # 手动创建一个 cache 记录来模拟
    async with handler._sessionmaker.begin() as session:
            # 先创建 rev 记录以满足外键约束
            dummy_rev = ThTransRev(
                project_id=req["project_id"],
                id="dummy_rev_id",
                content_id=content_id,
                target_lang="de",  # 添加target_lang字段
                revision_no=-1,
                status=TranslationStatus.DRAFT,
                src_payload_json={},
            )
            session.add(dummy_rev)
            await session.flush()  # 确保 dummy_rev 被写入数据库

            # 然后创建 cache 记录
            cache_entry = ThResolveCache(
                project_id=req["project_id"],
                content_id=content_id,
                target_lang="de",
                variant_key="-",
                resolved_rev_id=dummy_rev.id,
                resolved_payload={"text": "dummy"},
                expires_at=datetime.now(),
            )
            session.add(cache_entry)

    # 验证初始状态
    async with coordinator._sessionmaker() as session:
        assert (await session.get(ThContent, content_id)) is not None
        assert (
            await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))
        ).scalar_one_or_none() is not None
        assert (
            await session.execute(
                select(ThResolveCache).where(ThResolveCache.content_id == content_id)
            )
        ).scalar_one_or_none() is not None

    # 执行删除操作
    async with coordinator._sessionmaker.begin() as session:
        content_to_delete = await session.get(ThContent, content_id)
        await session.delete(content_to_delete)

    # 验证级联删除结果
    async with coordinator._sessionmaker() as session:
        assert (await session.get(ThContent, content_id)) is None
        assert (
            await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))
        ).scalar_one_or_none() is None
        assert (
            await session.execute(
                select(ThResolveCache).where(ThResolveCache.content_id == content_id)
            )
        ).scalar_one_or_none() is None
