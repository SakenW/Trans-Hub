# tests/integration/infrastructure/db/invariants/test_invariants_rls.py
"""
测试数据库架构中的不变式 (Invariants) - 行级安全 (RLS) (UoW 修复版)
"""

from __future__ import annotations
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from trans_hub.infrastructure.db._schema import ThContent
from trans_hub.infrastructure.uow import UowFactory

pytestmark = [pytest.mark.db, pytest.mark.invariants]

PROJECT_A = "rls_project_a"
PROJECT_B = "rls_project_b"


@pytest_asyncio.fixture
async def setup_rls_data(uow_factory: UowFactory):
    """
    (函数级) 使用【高权限】uow_factory 准备跨租户的数据。
    """
    async with uow_factory() as uow:
        await uow.misc.add_project_if_not_exists(PROJECT_A, "Project A")
        await uow.misc.add_project_if_not_exists(PROJECT_B, "Project B")
        await uow.content.add(
            project_id=PROJECT_A,
            namespace="test",
            keys_sha256_bytes=os.urandom(32),
            source_lang="en",
        )
        await uow.content.add(
            project_id=PROJECT_B,
            namespace="test",
            keys_sha256_bytes=os.urandom(32),
            source_lang="en",
        )


@pytest.mark.asyncio
async def test_rls_read_isolation(uow_factory_rls: UowFactory, setup_rls_data):
    """测试 RLS 的读取隔离。"""
    async with uow_factory_rls() as uow:
        await uow.session.execute(
            text(f"SET LOCAL th.allowed_projects = '{PROJECT_A}'")
        )
        result = await uow.session.execute(select(ThContent))
        # [修复] 使用 .scalars().all() 来明确获取 ORM 对象列表
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].project_id == PROJECT_A


@pytest.mark.asyncio
async def test_rls_write_isolation(uow_factory_rls: UowFactory, setup_rls_data):
    """测试 RLS 的写入隔离。"""
    async with uow_factory_rls() as uow:
        await uow.session.execute(
            text(f"SET LOCAL th.allowed_projects = '{PROJECT_A}'")
        )

        # [修复] 将预期失败的操作包裹在嵌套事务 (SAVEPOINT) 中
        with pytest.raises(
            DBAPIError, match="new row violates row-level security policy"
        ):
            async with uow.session.begin_nested():
                await uow.content.add(
                    project_id=PROJECT_B,  # 尝试写入不被允许的项目
                    namespace="malicious",
                    keys_sha256_bytes=os.urandom(32),
                    source_lang="en",
                )
        # 此处，顶级 uow 事务仍然是健康的


@pytest.mark.asyncio
async def test_rls_unrestricted_when_empty(uow_factory_rls: UowFactory, setup_rls_data):
    """测试 RLS 的“超级用户/维护模式”。"""
    async with uow_factory_rls() as uow:
        await uow.session.execute(text("SET LOCAL th.allowed_projects = ''"))
        result = await uow.session.execute(select(ThContent))
        # [修复] 使用 .scalars().all() 保持一致性
        rows = result.scalars().all()
        assert len(rows) >= 2
