# packages/server/tests/integration/infrastructure/db/repository/test_persistence_transactions.py
"""
测试持久化层 (Repository) 的复杂事务和原子性操作。

这些测试验证 PersistenceHandler 的核心方法在并发和事务边界下的行为是否正确。
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from trans_hub.infrastructure.db._schema import ThContent, ThProjects, ThTransHead, ThTransRev
from trans_hub.infrastructure.persistence import create_persistence_handler
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_get_or_create_head_is_atomic(db_sessionmaker: async_sessionmaker, test_config):
    """
    [核心验证] 验证 get_or_create_translation_head 在并发调用下是原子的，
    只会创建一个 head 和一个 initial revision。
    """
    project_id = f"atomic-proj-{uuid.uuid4().hex[:6]}"
    content_id = f"atomic-content-{uuid.uuid4().hex[:6]}"
    target_lang = "de"
    variant_key = "-"
    
    # 1. 准备基础数据
    async with db_sessionmaker.begin() as session:
        session.add(ThProjects(project_id=project_id, display_name="Atomic Test"))
        session.add(ThContent(id=content_id, project_id=project_id, namespace="atomic",
                              keys_sha256_bytes=b'\x20' * 32, source_lang="en"))

    # 2. 模拟并发调用
    handler = create_persistence_handler(test_config, db_sessionmaker)
    concurrency = 10
    tasks = [
        handler.get_or_create_translation_head(
            project_id=project_id,
            content_id=content_id,
            target_lang=target_lang,
            variant_key=variant_key,
        )
        for _ in range(concurrency)
    ]
    
    results = await asyncio.gather(*tasks)

    # 3. 验证结果
    # 3a. 所有调用都应该返回相同的 head_id 和 revision_no (0)
    first_head_id, first_rev_no = results[0]
    assert all(head_id == first_head_id for head_id, _ in results)
    assert all(rev_no == 0 for _, rev_no in results)
    
    # 3b. 数据库中物理上应该只有一个 head 和一个 revision
    async with db_sessionmaker() as session:
        head_count = await session.scalar(
            select(sa.func.count(ThTransHead.id)).where(ThTransHead.content_id == content_id)
        )
        rev_count = await session.scalar(
            select(sa.func.count(ThTransRev.id)).where(ThTransRev.content_id == content_id)
        )
        
        assert head_count == 1, "并发调用后只应该存在一个 Head 记录"
        assert rev_count == 1, "并发调用后只应该存在一个初始 Revision (rev_no=0)"


@pytest.mark.asyncio
async def test_create_new_revision_updates_head_in_transaction(db_sessionmaker: async_sessionmaker, test_config):
    """
    验证 create_new_translation_revision 是否在一个事务中同时创建 rev 并更新 head。
    """
    project_id = f"trans-proj-{uuid.uuid4().hex[:6]}"
    content_id = f"trans-content-{uuid.uuid4().hex[:6]}"
    
    handler = create_persistence_handler(test_config, db_sessionmaker)
    
    # 1. 准备初始状态：一个 head 和 rev_no=0
    async with db_sessionmaker.begin() as session:
        session.add(ThProjects(project_id=project_id, display_name="Transaction Test"))
        session.add(ThContent(id=content_id, project_id=project_id, namespace="atomic",
                              keys_sha256_bytes=b'\x21' * 32, source_lang="en",
                              source_payload_json={"text": "original"}))
    
    head_id, initial_rev_no = await handler.get_or_create_translation_head(
        project_id, content_id, "fr", "-"
    )
    assert initial_rev_no == 0
    
    # 2. 调用被测方法
    new_rev_id = await handler.create_new_translation_revision(
        head_id=head_id,
        project_id=project_id,
        content_id=content_id,
        target_lang="fr",
        variant_key="-",
        status=TranslationStatus.REVIEWED,
        revision_no=1,
        translated_payload_json={"text": "traduit"},
    )

    # 3. 验证数据库的最终状态
    async with db_sessionmaker() as session:
        # 3a. 验证新 revision 是否已创建
        new_rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == new_rev_id))).scalar_one_or_none()
        assert new_rev is not None
        assert new_rev.revision_no == 1
        
        # 3b. 验证 head 的指针是否已更新
        head = (await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))).scalar_one()
        assert head.current_rev_id == new_rev_id
        assert head.current_no == 1
        assert head.current_status == TranslationStatus.REVIEWED