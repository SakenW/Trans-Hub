# packages/server/tests/integration/infrastructure/db/invariants/test_invariants_triggers.py
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThEvents,
    ThProjects,
    ThResolveCache,
    ThTransHead,
    ThTransRev,
)
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.invariants]

# --- 夹具 ---

@pytest_asyncio.fixture
async def setup_trigger_base_data(db_sessionmaker: async_sessionmaker) -> dict:
    project_id = "trigger_proj"
    content_id = "content_for_trigger"
    rev1_id = "rev1_for_trigger"
    rev2_id = "rev2_for_trigger"
    head_id = "head_for_trigger"

    # [最终修复] 使用正确的参数名 db_sessionmaker
    async with db_sessionmaker.begin() as session:
        await session.execute(pg_insert(ThProjects).values(project_id=project_id, display_name="Trigger Test Project").on_conflict_do_nothing(index_elements=['project_id']))
        await session.execute(pg_insert(ThContent).values(id=content_id, project_id=project_id, namespace="triggers", keys_sha256_bytes=b'\x10' * 32, source_lang="en").on_conflict_do_nothing(index_elements=['id']))
        await session.execute(pg_insert(ThTransRev).values([
            {"project_id": project_id, "id": rev1_id, "content_id": content_id, "target_lang": "de", "revision_no": 1, "status": TranslationStatus.REVIEWED, "src_payload_json": {}},
            {"project_id": project_id, "id": rev2_id, "content_id": content_id, "target_lang": "de", "revision_no": 2, "status": TranslationStatus.REVIEWED, "src_payload_json": {}},
        ]).on_conflict_do_nothing(index_elements=['project_id', 'id']))
        await session.execute(pg_insert(ThTransHead).values(project_id=project_id, id=head_id, content_id=content_id, target_lang="de", current_rev_id=rev2_id, current_status=TranslationStatus.REVIEWED, current_no=2).on_conflict_do_nothing(index_elements=['project_id', 'id']))
    
    return {"project_id": project_id, "content_id": content_id, "rev1_id": rev1_id, "head_id": head_id}

# --- 测试用例 ---

@pytest.mark.asyncio
async def test_trigger_set_updated_at(db_sessionmaker: async_sessionmaker, setup_trigger_base_data: dict):
    content_id = setup_trigger_base_data["content_id"]
    
    # [最终修复] 使用显式的顶级事务块
    async with db_sessionmaker.begin() as session:
        select_stmt = select(ThContent.updated_at).where(ThContent.id == content_id)
        initial_updated_at = (await session.execute(select_stmt)).scalar_one()
        
        # 在同一个事务中，我们不需要 `asyncio.sleep`，因为 now() 会变化
        # 但保留它以确保时间差异足够大
        await asyncio.sleep(0.01)
        
        update_stmt = update(ThContent).where(ThContent.id == content_id).values(namespace="updated_namespace")
        await session.execute(update_stmt)
        
        # session.begin() 会在退出时自动 commit
    
    # 在一个新的会话/事务中验证结果，以确保数据已持久化
    async with db_sessionmaker() as session:
        final_updated_at = (await session.execute(select_stmt)).scalar_one()
        assert final_updated_at > initial_updated_at

@pytest.mark.asyncio
@pytest.mark.parametrize("input_variant, expected_variant", [
    ("Dark-Mode", "dark-mode"), ("  ", "-"), (None, "-"), ("normal", "normal"),
])
async def test_trigger_variant_normalize(db_sessionmaker: async_sessionmaker, setup_trigger_base_data: dict, input_variant: str | None, expected_variant: str):
    head_id = setup_trigger_base_data["head_id"]
    project_id = setup_trigger_base_data["project_id"]
    
    # [最终修复] 使用正确的参数名 db_sessionmaker
    async with db_sessionmaker.begin() as session:
        await session.execute(update(ThTransHead).where(ThTransHead.id == head_id, ThTransHead.project_id == project_id).values(variant_key=input_variant))
        
        select_stmt = select(ThTransHead.variant_key).where(ThTransHead.id == head_id, ThTransHead.project_id == project_id)
        normalized_variant = (await session.execute(select_stmt)).scalar_one()
        assert normalized_variant == expected_variant

@pytest.mark.asyncio
async def test_trigger_publish_flow(db_sessionmaker: async_sessionmaker, setup_trigger_base_data: dict):
    p_id = setup_trigger_base_data["project_id"]
    c_id = setup_trigger_base_data["content_id"]
    h_id = setup_trigger_base_data["head_id"]
    r1_id = setup_trigger_base_data["rev1_id"]
    
    # [最终修复] 使用正确的参数名 db_sessionmaker
    async with db_sessionmaker.begin() as session:
        await session.execute(pg_insert(ThResolveCache).values(
            project_id=p_id, content_id=c_id, target_lang="de", variant_key="-",
            resolved_rev_id=r1_id, resolved_payload={"text": "stale"},
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        ).on_conflict_do_update(index_elements=['project_id', 'content_id', 'target_lang', 'variant_key'], set_={'resolved_rev_id': r1_id}))
        
        cache_exists_result = await session.execute(select(ThResolveCache).where(ThResolveCache.content_id == c_id))
        assert cache_exists_result.first() is not None

        await session.execute(update(ThTransHead).where(ThTransHead.id == h_id, ThTransHead.project_id == p_id).values(published_rev_id=r1_id))
        
        event_stmt = select(ThEvents).where(ThEvents.head_id == h_id, ThEvents.event_type == 'published')
        
        event_result = await session.execute(event_stmt)
        row = event_result.first()
        event = row[0] if row else None
        
        assert event is not None, "应该创建一条 'published' 事件"
        assert isinstance(event, ThEvents), f"变量 'event' 应该是 ThEvents 对象, 但却是 {type(event)}"
        assert event.payload['new_rev'] == r1_id, "事件的 payload 应包含正确的 rev_id"

        cache_after_result = await session.execute(select(ThResolveCache).where(ThResolveCache.content_id == c_id))
        assert cache_after_result.first() is None, "缓存条目应该已被触发器删除"