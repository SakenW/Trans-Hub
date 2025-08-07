# tests/integration/test_coordinator_e2e.py
"""Trans-Hub 核心功能的端到端测试。"""

import asyncio
import importlib.util
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, cast

# [核心修复] 恢复缺失的导入
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from pytest_mock import MockerFixture

from trans_hub import Coordinator, EngineName
from trans_hub.core import (
    ContentItem,
    EngineSuccess,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.persistence.sqlite import SQLitePersistenceHandler

translators_is_available = importlib.util.find_spec("translators") is not None


@pytest.mark.asyncio
async def test_full_workflow_with_debug_engine(coordinator: Coordinator) -> None:
    # ... (rest of the file remains the same) ...
    business_id = "test.debug.hello"
    source_payload = {"text": "Hello"}
    target_lang = "zh-CN"
    await coordinator.request(
        business_id=business_id,
        source_payload=source_payload,
        target_langs=[target_lang],
    )
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.business_id == business_id
    assert result.translated_payload is not None
    assert "Translated(Hello)" in result.translated_payload.get("text", "")
    fetched_result = await coordinator.get_translation(business_id, target_lang)
    assert fetched_result is not None
    assert fetched_result.status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_request_with_specific_source_lang_overrides_global_config(
    coordinator: Coordinator, mocker: MockerFixture
) -> None:
    assert coordinator.config.source_lang == "en"

    mock_translate = mocker.patch.object(
        coordinator.active_engine,
        "atranslate_batch",
        new_callable=AsyncMock,
        return_value=[EngineSuccess(translated_text="mocked")],
    )

    business_id = "test.override.french_greeting"
    source_payload = {"text": "Bonjour"}
    target_lang = "de"
    override_source_lang = "fr"

    await coordinator.request(
        business_id=business_id,
        source_payload=source_payload,
        target_langs=[target_lang],
        source_lang=override_source_lang,
    )

    _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    mock_translate.assert_awaited_once()
    call_args = mock_translate.call_args
    assert call_args.kwargs["source_lang"] == override_source_lang
    assert call_args.kwargs["source_lang"] != coordinator.config.source_lang


@pytest.mark.asyncio
async def test_process_pending_handles_context_groups_concurrently(
    coordinator: Coordinator,
) -> None:
    ctx1 = {"id": "ctx1"}
    ctx2 = {"id": "ctx2"}
    await coordinator.request(
        "test.concurrent.ctx1", {"text": "text1"}, ["de"], context=ctx1
    )
    await coordinator.request(
        "test.concurrent.ctx2", {"text": "text2"}, ["de"], context=ctx2
    )
    processing_started_events = {
        "ctx1": asyncio.Event(),
        "ctx2": asyncio.Event(),
    }
    can_finish_event = asyncio.Event()

    original_process_batch = coordinator.processing_policy.process_batch

    async def controlled_process_batch(
        batch: list[ContentItem], *args: Any, **kwargs: Any
    ) -> list[TranslationResult]:
        context_id = (
            batch[0].context.get("id") if batch and batch[0].context else "unknown"
        )
        if context_id in processing_started_events:
            processing_started_events[context_id].set()
        await can_finish_event.wait()
        return await original_process_batch(batch, *args, **kwargs)

    async def consume_all() -> list[TranslationResult]:
        return [res async for res in coordinator.process_pending_translations("de")]

    with patch.object(
        coordinator.processing_policy,
        "process_batch",
        side_effect=controlled_process_batch,
    ):
        consumer_task = asyncio.create_task(consume_all())

        await asyncio.wait_for(processing_started_events["ctx1"].wait(), timeout=1)
        await asyncio.wait_for(processing_started_events["ctx2"].wait(), timeout=1)

        can_finish_event.set()
        results = await consumer_task

        assert len(results) == 2
        assert {res.original_payload["text"] for res in results} == {"text1", "text2"}


@pytest.mark.skipif(
    not os.getenv("TH_OPENAI_API_KEY"), reason="需要设置 TH_OPENAI_API_KEY"
)
@pytest.mark.asyncio
async def test_openai_engine_workflow(coordinator: Coordinator) -> None:
    await coordinator.switch_engine(EngineName.OPENAI.value)
    business_id = "test.openai.star"
    source_payload = {"text": "Star"}
    target_lang = "fr"
    context = {"system_prompt": "Translate the celestial body name."}

    await coordinator.request(
        business_id=business_id,
        source_payload=source_payload,
        target_langs=[target_lang],
        context=context,
    )
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED


@pytest.mark.skipif(
    not translators_is_available, reason="需要安装 'translators' 库才能运行此测试"
)
@pytest.mark.asyncio
async def test_translators_engine_workflow(coordinator: Coordinator) -> None:
    await coordinator.switch_engine(EngineName.TRANSLATORS.value)
    business_id = "test.translators.moon"
    source_payload = {"text": "Moon"}
    target_lang = "de"
    await coordinator.request(
        business_id=business_id,
        source_payload=source_payload,
        target_langs=[target_lang],
    )
    results = [
        res async for res in coordinator.process_pending_translations(target_lang)
    ]
    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED


@pytest.mark.asyncio
async def test_garbage_collection_workflow_and_date_boundary(
    coordinator: Coordinator,
) -> None:
    retention_days = 2
    now_for_test = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    stale_bid = "item.stale"
    stale_timestamp = datetime(2024, 1, 2, 23, 59, 59, tzinfo=timezone.utc)
    fresh_bid = "item.fresh"
    fresh_timestamp = datetime(2024, 1, 3, 0, 0, 0, tzinfo=timezone.utc)

    await coordinator.request(
        business_id=stale_bid, source_payload={"text": "stale"}, target_langs=["de"]
    )
    await coordinator.request(
        business_id=fresh_bid, source_payload={"text": "fresh"}, target_langs=["de"]
    )
    _ = [res async for res in coordinator.process_pending_translations("de")]

    handler = coordinator.handler
    assert isinstance(handler, SQLitePersistenceHandler)
    db_path = handler.db_path
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE th_jobs SET last_requested_at = ? WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = ?)",
            (stale_timestamp.isoformat(), stale_bid),
        )
        await db.execute(
            "UPDATE th_jobs SET last_requested_at = ? WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = ?)",
            (fresh_timestamp.isoformat(), fresh_bid),
        )
        await db.commit()

    await coordinator.run_garbage_collection(
        expiration_days=retention_days, dry_run=False, _now=now_for_test
    )

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM th_jobs WHERE content_id = (SELECT id FROM th_content WHERE business_id = ?)",
            (stale_bid,),
        )
        stale_job_count = await cursor.fetchone()
        assert stale_job_count is not None
        assert stale_job_count[0] == 0

        cursor = await db.execute(
            "SELECT COUNT(*) FROM th_jobs WHERE content_id = (SELECT id FROM th_content WHERE business_id = ?)",
            (fresh_bid,),
        )
        fresh_job_count = await cursor.fetchone()
        assert fresh_job_count is not None
        assert fresh_job_count[0] == 1

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM th_translations WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = ?)",
            (stale_bid,),
        )
        await db.commit()

    report2 = await coordinator.run_garbage_collection(
        expiration_days=retention_days, dry_run=False, _now=now_for_test
    )

    assert report2.get("deleted_content", 0) == 1
    assert (
        await coordinator.get_translation(business_id=stale_bid, target_lang="de")
        is None
    )
    assert (
        await coordinator.get_translation(business_id=fresh_bid, target_lang="de")
        is not None
    )


@pytest.mark.asyncio
async def test_graceful_shutdown(coordinator: Coordinator) -> None:
    business_id = "test.slow.translation"
    source_payload = {"text": "slow translation"}
    target_lang = "fr"
    await coordinator.request(
        business_id=business_id,
        source_payload=source_payload,
        target_langs=[target_lang],
    )

    processing_started = asyncio.Event()

    original_process_batch = coordinator.processing_policy.process_batch

    async def slow_process_batch(*args: Any, **kwargs: Any) -> list[TranslationResult]:
        processing_started.set()
        await asyncio.sleep(5)
        original_callable = cast(
            Callable[..., Awaitable[list[TranslationResult]]], original_process_batch
        )
        return await original_callable(*args, **kwargs)

    async def consume_worker() -> None:
        _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    with patch.object(
        coordinator.processing_policy, "process_batch", side_effect=slow_process_batch
    ):
        worker_task = asyncio.create_task(consume_worker())
        coordinator.track_task(worker_task)

        await processing_started.wait()

        close_task = asyncio.create_task(coordinator.close())

        await close_task

        assert worker_task.done()
        assert worker_task.cancelled()
        assert close_task.done()

        with pytest.raises(RuntimeError):
            await coordinator.get_translation(business_id, target_lang)
