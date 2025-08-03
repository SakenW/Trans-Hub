# tests/integration/test_coordinator_e2e.py
"""Trans-Hub 核心功能的端到端测试。"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import patch

import aiosqlite
import pytest

from trans_hub import Coordinator, EngineName
from trans_hub.interfaces import PersistenceHandler
from trans_hub.persistence import DefaultPersistenceHandler
from trans_hub.types import TranslationResult, TranslationStatus

# 定义测试常量
ENGINE_DEBUG = EngineName.DEBUG
ENGINE_TRANSLATORS = EngineName.TRANSLATORS
ENGINE_OPENAI = EngineName.OPENAI


@pytest.mark.asyncio
async def test_full_workflow_with_debug_engine(coordinator: Coordinator) -> None:
    """测试使用 Debug 引擎的完整翻译流程。

    Args:
        coordinator: 由 conftest.py 提供的、已初始化的真实 Coordinator 实例。
    """
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
    """测试 OpenAI 引擎的翻译流程（需要 API 密钥）。

    Args:
        coordinator: 由 conftest.py 提供的、已初始化的真实 Coordinator 实例。
    """
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
    """测试 Translators 引擎的翻译流程。

    Args:
        coordinator: 由 conftest.py 提供的、已初始化的真实 Coordinator 实例。
    """
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
    """测试垃圾回收（GC）能否正确清理过期和无关联的数据。

    Args:
        coordinator: 由 conftest.py 提供的、已初始化的真实 Coordinator 实例。
    """
    # 准备数据
    await coordinator.request(
        target_langs=["zh-CN"], text_content="fresh item", business_id="item.fresh"
    )
    await coordinator.request(
        target_langs=["zh-CN"], text_content="stale item", business_id="item.stale"
    )
    _ = [res async for res in coordinator.process_pending_translations("zh-CN")]

    # 手动将 "stale" 任务的时间戳设置为2天前
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

    # 运行 GC，只清理过期 job
    report1 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report1.get("deleted_jobs", 0) == 1
    assert report1.get("deleted_content", 0) == 0

    # 手动删除与 "stale" 内容关联的翻译记录，使其成为孤立内容
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

    # 再次运行 GC，清理孤立内容
    report2 = await coordinator.run_garbage_collection(dry_run=False, expiration_days=1)
    assert report2.get("deleted_jobs", 0) == 0
    assert report2.get("deleted_content", 0) == 1


@pytest.mark.asyncio
async def test_graceful_shutdown(coordinator: Coordinator) -> None:
    """测试优雅停机能否等待正在进行的任务完成。

    Args:
        coordinator: 由 conftest.py 提供的、已初始化的真实 Coordinator 实例。
    """
    text = "slow translation"
    target_lang = "fr"
    await coordinator.request(target_langs=[target_lang], text_content=text)

    processing_started = asyncio.Event()
    processing_can_finish = asyncio.Event()

    # 拦截原始的处理方法
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
        # 启动 worker
        worker_task: asyncio.Task[None] = asyncio.create_task(consume_worker())
        await processing_started.wait()

        # 在 worker 处理到一半时，请求关闭
        close_task = asyncio.create_task(coordinator.close())
        await asyncio.sleep(0.1)
        assert not close_task.done(), (
            "close() 应该在等待 active processor 完成，不应立即结束"
        )

        # 允许 worker 完成处理
        processing_can_finish.set()
        await worker_task

        # 在协调器完全关闭前，验证结果已写入数据库
        final_result = await coordinator.handler.get_translation(text, target_lang)
        assert final_result is not None
        assert final_result.status == TranslationStatus.TRANSLATED

        # 等待关闭任务最终完成
        await close_task
        assert close_task.done()