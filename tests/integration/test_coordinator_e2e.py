# tests/integration/test_coordinator_e2e.py
"""
Trans-Hub 核心功能的端到端测试。
v3.0.0 更新：全面重写以测试基于新架构的端到端工作流。
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from pytest_mock import MockerFixture

from trans_hub import Coordinator, EngineName
from trans_hub.core import (
    EngineSuccess,
    TranslationResult,
    TranslationStatus,
)
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


@pytest.mark.asyncio
async def test_request_with_specific_source_lang_overrides_global_config(
    coordinator: Coordinator, mocker: MockerFixture
) -> None:
    """测试在请求时指定 source_lang 能否正确覆盖全局配置。"""
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
async def test_garbage_collection_respects_date_boundary(
    coordinator: Coordinator,
) -> None:
    """测试垃圾回收（GC）能精确地根据日期边界清理过期数据。"""
    retention_days = 2
    now_for_test = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    
    stale_bid = "item.stale"
    stale_timestamp = now_for_test - timedelta(days=retention_days + 1)

    fresh_bid = "item.fresh"
    fresh_timestamp = now_for_test - timedelta(days=retention_days)

    # 第一步：创建所有数据
    for bid in [stale_bid, fresh_bid]:
        await coordinator.request(
            business_id=bid,
            source_payload={"text": bid},
            target_langs=["de"],
        )

    # 第二步：使用 handler 自身的连接和事务来更新时间戳
    handler = coordinator.handler
    assert isinstance(handler, SQLitePersistenceHandler)
    # 修复：移除多余的 type: ignore
    async with handler._transaction() as db:
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
    
    _ = [res async for res in coordinator.process_pending_translations("de")]

    # WHEN: 通过 Coordinator 的公共接口调用 GC，并注入 _now
    report = await coordinator.run_garbage_collection(
        expiration_days=retention_days, dry_run=False, _now=now_for_test
    )

    assert report.get("deleted_jobs", 0) == 1
    
    # 优化：使用 handler 的连接进行验证，确保单一连接
    # 修复：移除多余的 type: ignore
    async with handler._transaction() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM th_jobs")
        row = await cursor.fetchone()
        assert row is not None and row[0] == 1
        
        cursor = await db.execute(
            "SELECT c.business_id FROM th_jobs j JOIN th_content c ON j.content_id = c.id"
        )
        row = await cursor.fetchone()
        assert row is not None and row[0] == fresh_bid


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