# tests/test_main.py
"""Trans-Hub 核心功能的端到端测试。"""

import asyncio
import os
import shutil
import sqlite3
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import aiosqlite
import pytest
import pytest_asyncio
import structlog
from dotenv import load_dotenv

from trans_hub import Coordinator, EngineName, TransHubConfig
from trans_hub.db.schema_manager import MIGRATIONS_DIR
from trans_hub.interfaces import PersistenceHandler
from trans_hub.logging_config import setup_logging
from trans_hub.persistence import DefaultPersistenceHandler, create_persistence_handler
from trans_hub.types import TranslationResult, TranslationStatus

load_dotenv()
setup_logging(log_level="INFO", log_format="console")
logger = structlog.get_logger(__name__)

TEST_DIR = Path(__file__).parent / "test_output"
ENGINE_DEBUG = EngineName.DEBUG
ENGINE_TRANSLATORS = EngineName.TRANSLATORS
ENGINE_OPENAI = EngineName.OPENAI


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    TEST_DIR.mkdir(exist_ok=True)
    yield
    shutil.rmtree(TEST_DIR)


@pytest.fixture
def test_config() -> TransHubConfig:
    db_file = f"test_{os.urandom(4).hex()}.db"
    return TransHubConfig(
        database_url=f"sqlite:///{TEST_DIR / db_file}",
        active_engine=ENGINE_DEBUG,
        source_lang="en",
    )


@pytest_asyncio.fixture
async def coordinator(test_config: TransHubConfig) -> AsyncGenerator[Coordinator, None]:
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        raise RuntimeError("在 migrations 目录中找不到 SQL 迁移脚本。")
    latest_schema_file = migration_files[-1]
    sql_script = "\n".join(
        line
        for line in latest_schema_file.read_text("utf-8").splitlines()
        if not line.strip().startswith("--") and not line.strip().startswith("#")
    )
    conn = sqlite3.connect(test_config.db_path)
    conn.executescript(sql_script)
    conn.close()
    handler: PersistenceHandler = create_persistence_handler(test_config)
    coord = Coordinator(config=test_config, persistence_handler=handler)
    await coord.initialize()
    yield coord
    await coord.close()


@pytest.mark.asyncio
async def test_full_workflow_with_debug_engine(coordinator: Coordinator) -> None:
    text = "Hello"
    target_lang = "zh-CN"
    business_id = "test.debug.hello"
    await coordinator.request(
        target_langs=[target_lang], text_content=text, business_id=business_id
    )
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.business_id == business_id
    fetched_result = await coordinator.get_translation(text, target_lang)
    assert fetched_result is not None


@pytest.mark.skipif(
    not os.getenv("TH_OPENAI_API_KEY"), reason="需要设置 TH_OPENAI_API_KEY"
)
@pytest.mark.asyncio
async def test_openai_engine_workflow(coordinator: Coordinator) -> None:
    coordinator.switch_engine(ENGINE_OPENAI.value)
    text = "Star"
    target_lang = "fr"
    context = {"system_prompt": "Translate the celestial body name."}
    await coordinator.request(
        target_langs=[target_lang], text_content=text, context=context
    )
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_translators_engine_workflow(coordinator: Coordinator) -> None:
    coordinator.switch_engine(ENGINE_TRANSLATORS.value)
    text = "Moon"
    target_lang = "de"
    await coordinator.request(target_langs=[target_lang], text_content=text)
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_garbage_collection_workflow(coordinator: Coordinator) -> None:
    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )
    await coordinator.request(
        target_langs=["zh-CN"], text_content="stale item", business_id="item.stale"
    )
    _ = [res async for res in coordinator.process_pending_translations("zh-CN")]
    handler = coordinator.handler
    assert isinstance(handler, DefaultPersistenceHandler)
    db_path = handler.db_path
    async with aiosqlite.connect(db_path) as db:
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE th_jobs SET last_requested_at = ? WHERE business_id = ?",
            (two_days_ago, "item.stale"),
        )
        await db.commit()
    await coordinator.touch_jobs(["item.fresh"])
    report1 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report1["deleted_jobs"] == 1
    assert report1["deleted_content"] == 0
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT id FROM th_content WHERE value = 'stale item'"
        )
        row = await cursor.fetchone()
        assert row is not None
        stale_content_id = row[0]
        await db.execute(
            "DELETE FROM th_translations WHERE content_id = ?", (stale_content_id,)
        )
        await db.commit()
    report2 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report2["deleted_jobs"] == 0
    assert report2["deleted_content"] == 1


@pytest.mark.asyncio
async def test_force_retranslate_api(coordinator: Coordinator) -> None:
    text = "Sun"
    target_lang = "es"
    await coordinator.request(target_langs=[target_lang], text_content=text)
    _ = [res async for res in coordinator.process_pending_translations(target_lang)]
    result = await coordinator.get_translation(text, target_lang)
    assert result is not None and result.status == TranslationStatus.TRANSLATED
    await coordinator.request(
        target_langs=[target_lang], text_content=text, force_retranslate=True
    )
    handler = coordinator.handler
    assert isinstance(handler, DefaultPersistenceHandler)
    async with aiosqlite.connect(handler.db_path) as db:
        async with db.execute(
            "SELECT T.status FROM th_translations T JOIN th_content C ON T.content_id = C.id WHERE C.value = ?",
            (text,),
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None and row[0] == TranslationStatus.PENDING.value


@pytest.mark.asyncio
async def test_graceful_shutdown(coordinator: Coordinator) -> None:
    """测试优雅停机能否等待正在进行的任务完成。"""
    text = "slow translation"
    target_lang = "fr"
    await coordinator.request(target_langs=[target_lang], text_content=text)

    processing_started = asyncio.Event()
    processing_can_finish = asyncio.Event()

    original_process_batch = coordinator.processing_policy.process_batch

    async def slow_process_batch(*args: Any, **kwargs: Any) -> list[TranslationResult]:
        processing_started.set()
        await processing_can_finish.wait()
        original_callable = cast(
            Callable[..., Awaitable[list[TranslationResult]]], original_process_batch
        )
        return await original_callable(*args, **kwargs)

    async def consume_worker() -> None:
        _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    with patch.object(
        coordinator.processing_policy, "process_batch", side_effect=slow_process_batch
    ):
        worker_task: asyncio.Task[None] = asyncio.create_task(consume_worker())

        await processing_started.wait()

        close_task = asyncio.create_task(coordinator.close())

        await asyncio.sleep(0.1)
        assert not close_task.done(), (
            "close() 应该在等待 active processor 完成，不应立即结束"
        )

        processing_can_finish.set()

        # 等待处理完成
        await worker_task

        # 在协调器关闭前获取翻译结果
        final_result = await coordinator.handler.get_translation(text, target_lang)
        assert final_result is not None
        assert final_result.status == TranslationStatus.TRANSLATED

        await close_task

if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])