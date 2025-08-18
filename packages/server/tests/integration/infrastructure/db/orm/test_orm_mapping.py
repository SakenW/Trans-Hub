# tests/integration/infrastructure/db/orm/test_orm_mapping.py
"""
测试数据库架构中的 ORM 映射 (UoW 重构版)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThProjects,
    ThTransHead,
    ThTransRev,
)
from trans_hub.infrastructure.uow import UowFactory
from trans_hub_core.types import TranslationStatus

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_orm_mapping_core_tables(uow_factory: UowFactory):
    """
    通过在 UoW 中插入和立即取回一个复杂对象图，来验证核心表的 ORM 映射。
    """
    project_id = f"orm-proj-{uuid.uuid4().hex[:6]}"
    content_id = f"orm-content-{uuid.uuid4().hex[:6]}"
    rev_id = f"orm-rev-{uuid.uuid4().hex[:6]}"
    head_id = f"orm-head-{uuid.uuid4().hex[:6]}"

    # 准备 ORM 对象
    project = ThProjects(project_id=project_id, display_name="ORM Mapping Test")
    content = ThContent(
        id=content_id,
        project_id=project_id,
        namespace="orm.test",
        keys_sha256_bytes=b"\xab" * 32,
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

    # 1. 在 UoW 中插入对象图
    async with uow_factory() as uow:
        uow.session.add_all([project, content, revision, head])

    # 2. 在一个新的 UoW 中取回并验证
    async with uow_factory() as uow:
        retrieved_head_stmt = select(ThTransHead).where(ThTransHead.id == head_id)
        retrieved_head = (await uow.session.execute(retrieved_head_stmt)).scalar_one()

        assert retrieved_head.id == head_id
        assert retrieved_head.project_id == project_id
        assert retrieved_head.published_rev_id == rev_id
        assert retrieved_head.current_status == TranslationStatus.REVIEWED

        retrieved_rev_stmt = select(ThTransRev).where(ThTransRev.id == rev_id)
        retrieved_rev = (await uow.session.execute(retrieved_rev_stmt)).scalar_one()
        assert retrieved_rev.engine_name == "test-engine"
