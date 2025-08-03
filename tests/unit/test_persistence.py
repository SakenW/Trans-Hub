# tests/unit/test_persistence.py
"""针对 `trans_hub.persistence` 模块的单元测试。"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import patch

import aiosqlite
import pytest
import pytest_asyncio
from aiosqlite import Row

from trans_hub.db.schema_manager import MIGRATIONS_DIR
from trans_hub.persistence.sqlite import SQLitePersistenceHandler
from trans_hub.utils import get_context_hash


@pytest_asyncio.fixture
async def db_handler() -> AsyncGenerator[SQLitePersistenceHandler, None]:
    """提供一个使用内存数据库并应用了所有迁移的 SQLitePersistenceHandler。"""
    handler = SQLitePersistenceHandler(db_path=":memory:")
    await handler.connect()

    # v3.1 修复：对于内存数据库，直接在已建立的连接上执行迁移脚本
    # 这是测试内存数据库 schema 的最直接、最可靠的方法。
    sql_script = ""
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql_script += migration_file.read_text("utf-8")

    await handler.connection.executescript(sql_script)
    await handler.connection.commit()

    yield handler

    await handler.close()


@pytest.mark.asyncio
async def test_ensure_pending_creates_all_entities(
    db_handler: SQLitePersistenceHandler,
) -> None:
    """测试 ensure_pending_translations 是否能正确创建所有关联的数据库实体。"""
    text = "Hello UUID World"
    context = {"domain": "testing"}
    context_hash = get_context_hash(context)
    context_json = '{"domain": "testing"}'
    business_id = "test.uuid.hello"
    await db_handler.ensure_pending_translations(
        text_content=text,
        target_langs=["de"],
        source_lang="en",
        engine_version="3.0",
        business_id=business_id,
        context_hash=context_hash,
        context_json=context_json,
    )
    async with db_handler.connection.cursor() as cursor:
        cursor.row_factory = aiosqlite.Row
        await cursor.execute("SELECT id FROM th_content WHERE value = ?", (text,))
        content_row = await cursor.fetchone()
        assert content_row and isinstance(content_row["id"], str)