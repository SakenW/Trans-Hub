# tests/integration/infrastructure/db/invariants/test_invariants_triggers.py
"""
测试数据库架构中的不变式 (Invariants) - 触发器 (UoW 重构版)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update, insert

from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThEvents,
    ThResolveCache,
    ThTransHead,
    ThTransRev,
)
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.invariants]

# --- 夹具 ---


@pytest_asyncio.fixture
async def setup_trigger_base_data(uow_factory: UowFactory) -> dict:
    """
    (函数级) 使用 uow_factory 准备所有触发器测试所需的基础数据。
    """
    import uuid
    # 使用随机ID避免测试间的数据冲突
    suffix = uuid.uuid4().hex[:8]
    project_id = f"trigger_proj_{suffix}"
    content_id = f"content_for_trigger_{suffix}"
    rev1_id = f"rev1_for_trigger_{suffix}"
    rev2_id = f"rev2_for_trigger_{suffix}"
    head_id = f"head_for_trigger_{suffix}"

    async with uow_factory() as uow:
        # 使用仓库方法或原生 SQL 创建基础数据
        await uow.misc.add_project_if_not_exists(project_id, "Trigger Test Project")
        await uow.content.add(
            id=content_id,
            project_id=project_id,
            namespace="triggers",
            keys_sha256_bytes=b"\x10" * 32,
            source_lang="en",
            source_payload_json={},
        )

        # 无法直接使用仓库，因为需要指定 ID，所以用原生 insert
        await uow.session.execute(
            insert(ThTransRev).values(
                [
                    {
                        "project_id": project_id,
                        "id": rev1_id,
                        "content_id": content_id,
                        "target_lang": "de",
                        "revision_no": 1,
                        "status": TranslationStatus.REVIEWED,
                        "src_payload_json": {},
                    },
                    {
                        "project_id": project_id,
                        "id": rev2_id,
                        "content_id": content_id,
                        "target_lang": "de",
                        "revision_no": 2,
                        "status": TranslationStatus.REVIEWED,
                        "src_payload_json": {},
                    },
                ]
            )
        )
        await uow.session.execute(
            insert(ThTransHead).values(
                project_id=project_id,
                id=head_id,
                content_id=content_id,
                target_lang="de",
                current_rev_id=rev2_id,
                current_status=TranslationStatus.REVIEWED,
                current_no=2,
            )
        )

    return {
        "project_id": project_id,
        "content_id": content_id,
        "rev1_id": rev1_id,
        "rev2_id": rev2_id,
        "head_id": head_id,
    }


# --- 测试用例 ---


@pytest.mark.asyncio
async def test_trigger_set_updated_at(
    uow_factory: UowFactory, setup_trigger_base_data: dict
):
    content_id = setup_trigger_base_data["content_id"]

    async with uow_factory() as uow:
        select_stmt = select(ThContent.updated_at).where(ThContent.id == content_id)
        initial_updated_at = (await uow.session.execute(select_stmt)).scalar_one()

        await asyncio.sleep(0.01)  # 确保时间戳有足够差异

        update_stmt = (
            update(ThContent)
            .where(ThContent.id == content_id)
            .values(namespace="updated_namespace")
        )
        await uow.session.execute(update_stmt)

        # 在同一个事务中再次查询，以验证更新时的行为
        final_updated_at = (await uow.session.execute(select_stmt)).scalar_one()
        assert final_updated_at > initial_updated_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input_variant, expected_variant",
    [
        ("Dark-Mode", "dark-mode"),
        ("  ", "-"),
        (None, "-"),
        ("normal", "normal"),
    ],
)
async def test_trigger_variant_normalize(
    uow_factory: UowFactory,
    setup_trigger_base_data: dict,
    input_variant: str | None,
    expected_variant: str,
):
    head_id = setup_trigger_base_data["head_id"]
    project_id = setup_trigger_base_data["project_id"]

    async with uow_factory() as uow:
        await uow.session.execute(
            update(ThTransHead)
            .where(ThTransHead.id == head_id, ThTransHead.project_id == project_id)
            .values(variant_key=input_variant)
        )

        select_stmt = select(ThTransHead.variant_key).where(
            ThTransHead.id == head_id, ThTransHead.project_id == project_id
        )
        normalized_variant = (await uow.session.execute(select_stmt)).scalar_one()
        assert normalized_variant == expected_variant


@pytest.mark.asyncio
async def test_trigger_publish_flow(
    uow_factory: UowFactory, setup_trigger_base_data: dict
):
    p_id = setup_trigger_base_data["project_id"]
    c_id = setup_trigger_base_data["content_id"]
    h_id = setup_trigger_base_data["head_id"]
    r1_id = setup_trigger_base_data["rev1_id"]

    async with uow_factory() as uow:
        # 准备：在缓存中放一条数据
        await uow.session.execute(
            insert(ThResolveCache).values(
                project_id=p_id,
                content_id=c_id,
                target_lang="de",
                variant_key="-",
                resolved_rev_id=r1_id,
                resolved_payload={"text": "stale"},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        assert (await uow.session.execute(select(ThResolveCache))).first() is not None

        # 核心操作：执行发布
        await uow.session.execute(
            update(ThTransHead)
            .where(ThTransHead.id == h_id, ThTransHead.project_id == p_id)
            .values(published_rev_id=r1_id)
        )

        # 验证事件
        event = (
            await uow.session.execute(
                select(ThEvents).where(
                    ThEvents.head_id == h_id, ThEvents.event_type == "published"
                )
            )
        ).scalar_one_or_none()

        assert event is not None, "应该创建一条 'published' 事件"
        assert event.payload["new_rev"] == r1_id, "事件的 payload 应包含正确的 rev_id"

        # 验证缓存失效
        cache_after = (await uow.session.execute(select(ThResolveCache))).first()
        assert cache_after is None, "缓存条目应该已被触发器删除"


@pytest.mark.asyncio
async def test_trigger_unpublish_flow(
    uow_factory: UowFactory, setup_trigger_base_data: dict
):
    """验证撤回发布时的触发器行为：创建 'unpublished' 事件 + 删除缓存。"""
    p_id = setup_trigger_base_data["project_id"]
    c_id = setup_trigger_base_data["content_id"]
    h_id = setup_trigger_base_data["head_id"]
    r1_id = setup_trigger_base_data["rev1_id"]

    async with uow_factory() as uow:
        # 准备：
        # 1a. 先将 head 设置为已发布状态
        await uow.session.execute(
            update(ThTransHead)
            .where(ThTransHead.id == h_id, ThTransHead.project_id == p_id)
            .values(published_rev_id=r1_id)
        )
        # 1b. 在缓存中放入一条数据
        await uow.session.execute(
            insert(ThResolveCache).values(
                project_id=p_id,
                content_id=c_id,
                target_lang="de",
                variant_key="-",
                resolved_rev_id=r1_id,
                resolved_payload={"text": "published"},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )

        # 核心操作：执行撤回发布
        await uow.session.execute(
            update(ThTransHead)
            .where(ThTransHead.id == h_id, ThTransHead.project_id == p_id)
            .values(published_rev_id=None)  # <-- 撤回发布
        )

        # 验证事件
        event = (
            await uow.session.execute(
                select(ThEvents).where(
                    ThEvents.head_id == h_id, ThEvents.event_type == "unpublished"
                )
            )
        ).scalar_one_or_none()

        assert event is not None, "应该创建一条 'unpublished' 事件"
        assert event.payload["old_rev"] == r1_id, "事件的 payload 应包含正确的 old_rev"

        # 验证缓存失效
        cache_after = (await uow.session.execute(select(ThResolveCache))).first()
        assert cache_after is None, "缓存条目应该已被触发器删除"
