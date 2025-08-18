# packages/server/tests/integration/persistence/test_repositories.py
"""
对持久化层（仓库）进行集成测试 (UoW 重构版)。
这些测试验证每个仓库方法是否能正确地与真实数据库交互。
"""

import os  # [修复] 导入 os 以生成随机字节
import uuid
import pytest
from sqlalchemy import select, func

from trans_hub.infrastructure.db._schema import (
    ThTransHead,
    ThTransRev,
)
from trans_hub.infrastructure.uow import UowFactory

pytestmark = [pytest.mark.db, pytest.mark.integration]


@pytest.mark.asyncio
async def test_content_repo_add_and_get(uow_factory: UowFactory):
    """验证 Content 仓库的添加和查询功能。"""
    project_id = "repo-test-proj"
    namespace = "repo.test"
    # [修复] 使用 os.urandom(32) 生成正确的 32 字节哈希
    keys_sha = os.urandom(32)

    async with uow_factory() as uow:
        await uow.misc.add_project_if_not_exists(project_id, "Repo Test")
        content_id = await uow.content.add(
            project_id=project_id,
            namespace=namespace,
            keys_sha256_bytes=keys_sha,
            source_lang="en",
            source_payload_json={"text": "hello"},
        )

    async with uow_factory() as uow:
        retrieved_id = await uow.content.get_id_by_uida(project_id, namespace, keys_sha)
        assert retrieved_id == content_id


@pytest.mark.asyncio
async def test_translation_repo_get_or_create_head_is_atomic(uow_factory: UowFactory):
    """验证 get_or_create_head 在同一个事务中是幂等的。"""
    project_id = "repo-atomic-proj"
    content_id = str(uuid.uuid4())

    async with uow_factory() as uow:
        # 准备基础数据
        await uow.misc.add_project_if_not_exists(project_id, "Atomic Repo Test")

        # [修复] 调用 add 时不再传入 id，让仓库方法自己处理
        await uow.content.add(
            id=content_id,  # [修正] content.add 已经修复，可以接收 id
            project_id=project_id,
            namespace="atomic",
            keys_sha256_bytes=os.urandom(32),  # [修复] 使用正确的 32 字节
            source_lang="en",
        )

        # 在同一个 UoW (事务) 中多次调用
        head_id1, rev_no1 = await uow.translations.get_or_create_head(
            project_id, content_id, "de", "-"
        )
        head_id2, rev_no2 = await uow.translations.get_or_create_head(
            project_id, content_id, "de", "-"
        )

        assert head_id1 == head_id2
        assert rev_no1 == rev_no2 == 0

    # 验证最终结果
    async with uow_factory() as uow:
        # [修改] 直接使用 uow.session，不再需要 begin()
        head_count = await uow.session.scalar(
            select(func.count(ThTransHead.id)).where(
                ThTransHead.content_id == content_id
            )
        )
        rev_count = await uow.session.scalar(
            select(func.count(ThTransRev.id)).where(ThTransRev.content_id == content_id)
        )
        assert head_count == 1
        assert rev_count == 1
