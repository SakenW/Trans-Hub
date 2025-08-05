# tests/integration/test_coordinator_e2e.py
"""
Trans-Hub 核心功能的端到端测试。
v3.0.0 更新：全面重写以测试基于新架构的端到端工作流。
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import patch

import aiosqlite
import pytest

from trans_hub import Coordinator, EngineName
from trans_hub.core import TranslationResult, TranslationStatus
from trans_hub.persistence.sqlite import SQLitePersistenceHandler


@pytest.mark.asyncio
async def test_full_workflow_with_debug_engine(coordinator: Coordinator) -> None:
    """测试使用 Debug 引擎的完整翻译流程。"""
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


@pytest.mark.skipif(
    not os.getenv("TH_OPENAI_API_KEY"), reason="需要设置 TH_OPENAI_API_KEY"
)
@pytest.mark.asyncio
async def test_openai_engine_workflow(coordinator: Coordinator) -> None:
    """测试 OpenAI 引擎的翻译流程（需要 API 密钥）。"""
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


@pytest.mark.asyncio
async def test_translators_engine_workflow(coordinator: Coordinator) -> None:
    """测试 Translators 引擎的翻译流程。"""
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
async def test_garbage_collection_workflow(coordinator: Coordinator) -> None:
    """测试垃圾回收（GC）能否正确清理过期和无关联的数据。"""
    await coordinator.request(
        business_id="item.fresh",
        source_payload={"text": "fresh item"},
        target_langs=["zh-CN"],
    )
    await coordinator.request(
        business_id="item.stale",
        source_payload={"text": "stale item"},
        target_langs=["zh-CN"],
    )
    _ = [res async for res in coordinator.process_pending_translations("zh-CN")]

    handler = coordinator.handler
    assert isinstance(handler, SQLitePersistenceHandler)
    db_path = handler.db_path
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT id FROM th_content WHERE business_id = 'item.stale'"
        )
        row = await cursor.fetchone()
        assert row is not None
        stale_content_id = row[0]

        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.execute(
            "UPDATE th_jobs SET last_requested_at = ? WHERE content_id = ?",
            (two_days_ago, stale_content_id),
        )
        await db.commit()

    report1 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report1.get("deleted_jobs", 0) == 1

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM th_translations WHERE content_id = (SELECT id FROM th_content WHERE business_id = 'item.stale')"
        )
        await db.commit()

    report2 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report2.get("deleted_content", 0) == 1


@pytest.mark.asyncio
async def test_graceful_shutdown(coordinator: Coordinator) -> None:
    """测试优雅停机能否正确取消正在进行的任务并安全关闭。"""
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
        # v3.5.6 修复：移除 try/except，让 CancelledError 自然传播
        _ = [res async for res in coordinator.process_pending_translations(target_lang)]

    with patch.object(
        coordinator.processing_policy, "process_batch", side_effect=slow_process_batch
    ):
        worker_task = asyncio.create_task(consume_worker())
        coordinator.track_task(worker_task)
        
        await processing_started.wait()

        close_task = asyncio.create_task(coordinator.close())
        
        # v3.5.6 修复：等待 close() 完成，它会负责取消和等待 worker
        await close_task
        
        assert worker_task.done()
        assert worker_task.cancelled()
        assert close_task.done()
        
        with pytest.raises(RuntimeError):
            await coordinator.get_translation(business_id, target_lang)
