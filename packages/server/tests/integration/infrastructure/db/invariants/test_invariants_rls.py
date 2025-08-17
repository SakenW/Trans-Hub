# packages/server/tests/integration/infrastructure/db/invariants/test_invariants_rls.py
"""
测试数据库架构中的不变式 (Invariants) - 行级安全 (RLS)
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from trans_hub.infrastructure.db._schema import ThContent, ThProjects

pytestmark = [pytest.mark.db, pytest.mark.invariants]

PROJECT_A = "rls_project_a"
PROJECT_B = "rls_project_b"

@pytest_asyncio.fixture
async def setup_rls_data(migrated_db: AsyncEngine):
    """
    使用【高权限】引擎准备跨租户的数据。
    """
    async with migrated_db.begin() as conn:
        await conn.execute(insert(ThProjects).values([
            {"project_id": PROJECT_A, "display_name": "Project A"},
            {"project_id": PROJECT_B, "display_name": "Project B"},
        ]).on_conflict_do_nothing())

        await conn.execute(insert(ThContent).values([
            {
                "id": str(uuid.uuid4()), "project_id": PROJECT_A, "namespace": "test",
                "keys_sha256_bytes": b'\x01' * 32, "source_lang": "en",
            },
            {
                "id": str(uuid.uuid4()), "project_id": PROJECT_B, "namespace": "test",
                "keys_sha256_bytes": b'\x02' * 32, "source_lang": "en",
            }
        ]).on_conflict_do_nothing(index_elements=['project_id', 'namespace', 'keys_sha256_bytes']))
    return

@pytest.mark.asyncio
async def test_rls_read_isolation(rls_engine: AsyncEngine, setup_rls_data):
    """
    [已通过] 测试 RLS 的读取隔离。
    """
    async with rls_engine.connect() as conn:
        await conn.execute(text(f"SET th.allowed_projects = '{PROJECT_A}'"))
        result = await conn.execute(select(ThContent))
        rows = result.all()
        assert len(rows) == 1
        assert rows[0].project_id == PROJECT_A
        await conn.execute(text("RESET th.allowed_projects"))

@pytest.mark.asyncio
async def test_rls_write_isolation(rls_engine: AsyncEngine, setup_rls_data):
    """
    [核心验证] 测试 RLS 的写入隔离。
    """
    # [最终修复] 使用 conn.begin() 来管理整个测试的顶级事务
    async with rls_engine.connect() as conn:
        async with conn.begin(): # 显式开启一个顶级事务
            await conn.execute(text(f"SET th.allowed_projects = '{PROJECT_A}'"))
            
            malicious_insert_stmt = insert(ThContent).values(
                id=str(uuid.uuid4()),
                project_id=PROJECT_B,
                namespace="malicious",
                keys_sha256_bytes=b'\x03' * 32,
                source_lang="en",
            )
            
            # 使用嵌套事务 (SAVEPOINT) 来隔离可能失败的操作
            with pytest.raises(DBAPIError, match="new row violates row-level security policy"):
                async with conn.begin_nested():
                    await conn.execute(malicious_insert_stmt)
                # 这个块出错时，只会回滚到 SAVEPOINT，外层事务依然有效
            
            # 这个 RESET 语句现在可以成功执行
            await conn.execute(text("RESET th.allowed_projects"))
        # 顶级事务在这里结束 (commit)

@pytest.mark.asyncio
async def test_rls_unrestricted_when_empty(rls_engine: AsyncEngine, setup_rls_data):
    """
    [已通过] 测试 RLS 的“超级用户/维护模式”。
    """
    async with rls_engine.connect() as conn:
        await conn.execute(text("SET th.allowed_projects = ''"))
        result = await conn.execute(select(ThContent))
        rows = result.all()
        assert len(rows) == 2
        await conn.execute(text("RESET th.allowed_projects"))