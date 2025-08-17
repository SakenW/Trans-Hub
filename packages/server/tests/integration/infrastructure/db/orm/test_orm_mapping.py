# packages/server/tests/integration/infrastructure/db/orm/test_orm_mapping.py
"""
测试数据库架构中的 ORM 映射

这些测试验证 SQLAlchemy 的 ORM 模型 (`_schema.py`) 是否与由 Alembic
迁移脚本创建的物理数据库表的结构（列名、类型、约束）完全一致。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThProjects,
    ThTransHead,
    ThTransRev,
)
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_orm_mapping_core_tables(db_sessionmaker: async_sessionmaker):
    """
    通过插入和立即取回一个包含所有字段的复杂对象，来验证核心表的 ORM 映射。
    """
    project_id = f"orm-proj-{uuid.uuid4().hex[:6]}"
    content_id = f"orm-content-{uuid.uuid4().hex[:6]}"
    rev_id = f"orm-rev-{uuid.uuid4().hex[:6]}"
    head_id = f"orm-head-{uuid.uuid4().hex[:6]}"
    
    # 准备一个包含所有非空字段的对象图
    project = ThProjects(project_id=project_id, display_name="ORM Mapping Test")
    content = ThContent(
        id=content_id,
        project_id=project_id,
        namespace="orm.test",
        keys_sha256_bytes=b'\xAB' * 32,
        source_lang="en-US",
        source_payload_json={"title": "Hello"},
    )
    revision = ThTransRev(
        project_id=project_id,
        id=rev_id,
        content_id=content_id,
        target_lang="de-DE",
        variant_key="test-variant",
        revision_no=1,
        status=TranslationStatus.REVIEWED,
        origin_lang="en-US",
        src_payload_json={"title": "Hello"},
        translated_payload_json={"title": "Hallo"},
        engine_name="test-engine",
        engine_version="1.0",
    )
    head = ThTransHead(
        project_id=project_id,
        id=head_id,
        content_id=content_id,
        target_lang="de-DE",
        variant_key="test-variant",
        current_rev_id=rev_id,
        current_status=TranslationStatus.REVIEWED,
        current_no=1,
        published_rev_id=rev_id,
        published_no=1,
        published_at=datetime.now(timezone.utc),
    )

    # 1. 插入对象图
    async with db_sessionmaker.begin() as session:
        session.add_all([project, content, revision, head])

    # 2. 在一个新的会话中取回并验证
    async with db_sessionmaker() as session:
        retrieved_head = (
            await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))
        ).scalar_one()

        # 断言几个关键字段以确认映射正确
        assert retrieved_head.id == head_id
        assert retrieved_head.project_id == project_id
        assert retrieved_head.published_rev_id == rev_id
        assert retrieved_head.current_status == TranslationStatus.REVIEWED

        # 验证关联对象是否也能被正确加载（如果配置了 relationship）
        # 或者直接查询
        retrieved_rev = (
            await session.execute(select(ThTransRev).where(ThTransRev.id == rev_id))
        ).scalar_one()
        assert retrieved_rev.engine_name == "test-engine"