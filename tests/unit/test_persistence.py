# tests/unit/test_persistence.py
"""针对 `trans_hub.persistence` 模块的单元测试。"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import patch

import pytest
import pytest_asyncio
from aiosqlite import Row

from trans_hub.db.schema_manager import MIGRATIONS_DIR
from trans_hub.persistence.sqlite import SQLitePersistenceHandler
from trans_hub.utils import get_context_hash


@pytest_asyncio.fixture
async def db_handler() -> AsyncGenerator[SQLitePersistenceHandler, None]:
    handler = SQLitePersistenceHandler(db_path=":memory:")
    await handler.connect()
    migration_file = sorted(MIGRATIONS_DIR.glob("*.sql"))[-1]
    sql_script = "\n".join(
        line
        for line in migration_file.read_text("utf-8").splitlines()
        if not line.strip().startswith("#")
    )
    await handler.connection.executescript(sql_script)
    await handler.connection.commit()
    yield handler
    await handler.close()


@pytest.mark.asyncio
async def test_ensure_pending_creates_all_entities(
    db_handler: SQLitePersistenceHandler,
) -> None:
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
        await cursor.execute("SELECT id FROM th_content WHERE value = ?", (text,))
        content_row = await cursor.fetchone()
        assert content_row and isinstance(content_row["id"], str)
        content_id = content_row["id"]
        await cursor.execute(
            "SELECT id FROM th_contexts WHERE context_hash = ?", (context_hash,)
        )
        context_row = await cursor.fetchone()
        assert context_row and isinstance(context_row["id"], str)
        context_id = context_row["id"]
        await cursor.execute(
            "SELECT content_id, context_id FROM th_jobs WHERE business_id = ?",
            (business_id,),
        )
        job_row = await cursor.fetchone()
        assert (
            job_row
            and job_row["content_id"] == content_id
            and job_row["context_id"] == context_id
        )
        await cursor.execute(
            "SELECT id FROM th_translations WHERE content_id = ? AND context_id = ? AND lang_code = 'de'",
            (content_id, context_id),
        )
        assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_upsert_logic_for_jobs(db_handler: SQLitePersistenceHandler) -> None:
    text = "Recurring Request"
    business_id = "test.recurring"
    time1 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    time2 = datetime(2025, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
    with patch("trans_hub.persistence.sqlite.datetime") as mock_dt:
        mock_dt.now.return_value = time1
        await db_handler.ensure_pending_translations(
            text, ["en"], "en", "3.0", business_id
        )
    async with db_handler.connection.execute(
        "SELECT id, last_requested_at FROM th_jobs"
    ) as c:
        job1 = await c.fetchone()
        assert job1 and job1["last_requested_at"] == time1.isoformat()
    with patch("trans_hub.persistence.sqlite.datetime") as mock_dt:
        mock_dt.now.return_value = time2
        await db_handler.ensure_pending_translations(
            text, ["en"], "en", "3.0", business_id
        )
    async with db_handler.connection.execute(
        "SELECT id, last_requested_at FROM th_jobs"
    ) as c:
        job2 = await c.fetchone()
        assert job2 and job2["last_requested_at"] == time2.isoformat()
    assert job1 and job2 and job1["id"] == job2["id"]
    assert job1["last_requested_at"] < job2["last_requested_at"]
    async with db_handler.connection.execute("SELECT COUNT(*) FROM th_jobs") as c:
        count = await c.fetchone()
        assert count and count[0] == 1


@pytest.mark.asyncio
async def test_null_context_handling(db_handler: SQLitePersistenceHandler) -> None:
    await db_handler.ensure_pending_translations(
        "Global Text", ["fr"], "en", "3.0", "global.text", get_context_hash(None)
    )
    async with db_handler.connection.cursor() as cursor:
        await cursor.execute(
            "SELECT context_id FROM th_jobs WHERE business_id = 'global.text'"
        )
        job_row = await cursor.fetchone()
        assert job_row and job_row["context_id"] is None
        await cursor.execute(
            "SELECT context_id FROM th_translations WHERE lang_code = 'fr'"
        )
        translation_row = await cursor.fetchone()
        assert translation_row and translation_row["context_id"] is None


@pytest.mark.asyncio
async def test_touch_jobs_updates_timestamp(
    db_handler: SQLitePersistenceHandler,
) -> None:
    business_id_1 = "touch.test.1"
    business_id_2 = "touch.test.2"
    await db_handler.ensure_pending_translations(
        "Touch Text 1", ["en"], "en", "3.0", business_id_1
    )
    await db_handler.ensure_pending_translations(
        "Touch Text 2", ["en"], "en", "3.0", business_id_2
    )

    async with db_handler.connection.execute(
        "SELECT last_requested_at FROM th_jobs WHERE business_id = ?", (business_id_1,)
    ) as c:
        # --- 最终修复：添加 None 检查 ---
        time1_before_row: Optional[Row] = await c.fetchone()
        assert time1_before_row is not None
        time1_before = time1_before_row[0]

    time_after_touch = datetime.now(timezone.utc) + timedelta(seconds=1)

    with patch("trans_hub.persistence.sqlite.datetime") as mock_dt:
        mock_dt.now.return_value = time_after_touch
        await db_handler.touch_jobs([business_id_1, business_id_2])

    async with db_handler.connection.execute(
        "SELECT last_requested_at FROM th_jobs WHERE business_id = ?", (business_id_1,)
    ) as c:
        # --- 最终修复：添加 None 检查 ---
        time1_after_row: Optional[Row] = await c.fetchone()
        assert time1_after_row is not None
        time1_after = time1_after_row[0]

    assert time1_after > time1_before
    assert time1_after == time_after_touch.isoformat()
