# tests/integration/test_coordinator_e2e.py
"""
Trans-Hub 核心功能的端到端测试。
v3.0.0 更新：全面重写以测试基于新架构的端到端工作流。
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, cast
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
    # GIVEN: 全局 source_lang 在 test_config fixture 中被设为 "en"
    assert coordinator.config.source_lang == "en"

    # 准备 mock
    mock_translate = mocker.patch.object(
        coordinator.active_engine,
        "atranslate_batch",
        new_callable=AsyncMock,
        return_value=[EngineSuccess(translated_text="mocked")],
    )

    # WHEN: 发起一个指定了不同 source_lang 的请求
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

    # THEN: 验证引擎被调用时，使用的是覆盖后的 source_lang
    mock_translate.assert_awaited_once()
    call_args = mock_translate.call_args
    assert call_args.kwargs["source_lang"] == override_source_lang
    assert call_args.kwargs["source_lang"] != coordinator.config.source_lang


@pytest.mark.asyncio
async def test_process_pending_handles_context_groups_concurrently(
    coordinator: Coordinator,
) -> None:
    """验证 Coordinator 能并发处理不同上下文的任务小组，而不是串行阻塞。"""
    # GIVEN: 两个不同上下文的翻译请求
    ctx1 = {"id": "ctx1"}
    ctx2 = {"id": "ctx2"}
    await coordinator.request(
        "test.concurrent.ctx1", {"text": "text1"}, ["de"], context=ctx1
    )
    await coordinator.request(
        "test.concurrent.ctx2", {"text": "text2"}, ["de"], context=ctx2
    )

    # 用 Events 来控制和观察 mock 函数的执行流程
    processing_started_events = {
        "ctx1": asyncio.Event(),
        "ctx2": asyncio.Event(),
    }
    can_finish_event = asyncio.Event()

    original_process_batch = coordinator.processing_policy.process_batch

    async def controlled_process_batch(
        batch: list[ContentItem], *args: Any, **kwargs: Any
    ) -> list[TranslationResult]:
        # 识别当前批次属于哪个上下文
        context_id = (
            batch[0].context.get("id") if batch and batch[0].context else "unknown"
        )
        # 发出“已开始处理”信号
        if context_id in processing_started_events:
            processing_started_events[context_id].set()
        # 等待“可以完成”的信号
        await can_finish_event.wait()
        # 调用原始实现来返回有效结果
        return await original_process_batch(batch, *args, **kwargs)

    async def consume_all() -> list[TranslationResult]:
        return [res async for res in coordinator.process_pending_translations("de")]

    with patch.object(
        coordinator.processing_policy,
        "process_batch",
        side_effect=controlled_process_batch,
    ):
        # WHEN: 在后台启动 worker
        consumer_task = asyncio.create_task(consume_all())

        # THEN: 验证两个上下文小组都已开始处理，即使我们还未允许任何一个完成
        # 这证明了它们是并发启动的
        await asyncio.wait_for(processing_started_events["ctx1"].wait(), timeout=1)
        await asyncio.wait_for(processing_started_events["ctx2"].wait(), timeout=1)

        # 现在，允许所有处理完成
        can_finish_event.set()
        results = await consumer_task

        # 最终验证结果
        assert len(results) == 2
        assert {res.original_payload["text"] for res in results} == {"text1", "text2"}


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
async def test_garbage_collection_workflow_and_date_boundary(
    coordinator: Coordinator,
) -> None:
    """测试垃圾回收（GC）能精确地根据日期边界清理过期数据，并验证完整清理流程。"""
    # GIVEN: 准备测试数据和确定的时间
    retention_days = 2
    now_for_test = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    # cutoff_date 的计算结果应该是 2024-01-03。任何在此日期之前的数据都应被删除。

    stale_bid = "item.stale"
    # --- 核心修复：此项时间戳现在明确早于截止日期 ---
    stale_timestamp = datetime(2024, 1, 2, 23, 59, 59, tzinfo=timezone.utc)

    fresh_bid = "item.fresh"
    # --- 核心修复：此项时间戳现在正好是截止日期的第一秒，不应被删除 ---
    fresh_timestamp = datetime(2024, 1, 3, 0, 0, 0, tzinfo=timezone.utc)

    # ... (测试的其余部分保持不变) ...
    # 步骤 1: 创建所有数据
    await coordinator.request(
        business_id=stale_bid, source_payload={"text": "stale"}, target_langs=["de"]
    )
    await coordinator.request(
        business_id=fresh_bid, source_payload={"text": "fresh"}, target_langs=["de"]
    )
    _ = [res async for res in coordinator.process_pending_translations("de")]

    # 步骤 2: 手动设置时间戳
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

    # WHEN: 运行第一次GC
    report1 = await coordinator.run_garbage_collection(
        expiration_days=retention_days, dry_run=False, _now=now_for_test
    )
    # THEN: 验证只有过期的 job 被删除
    assert report1.get("deleted_jobs", 0) == 1
    assert report1.get("deleted_content", 0) == 0

    # 步骤 3: 手动移除与 stale_bid 关联的翻译记录，使其成为孤立内容
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM th_translations WHERE content_id = "
            "(SELECT id FROM th_content WHERE business_id = ?)",
            (stale_bid,),
        )
        await db.commit()

    # WHEN: 运行第二次GC，现在应该能删除孤立的 content
    report2 = await coordinator.run_garbage_collection(
        expiration_days=retention_days, dry_run=False, _now=now_for_test
    )
    # THEN: 验证孤立的 content 被删除
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
