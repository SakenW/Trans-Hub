# tests/unit/engines/test_engine_functionality.py
"""
测试翻译引擎的核心功能，包括速率限制、并发控制和翻译执行。
"""

import asyncio
from typing import Any, AsyncGenerator, Optional
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pytest_mock import MockerFixture

from trans_hub.core.types import EngineBatchItemResult, EngineError, EngineSuccess
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.rate_limiter import RateLimiter


class _TestEngineConfig(BaseEngineConfig):
    """测试引擎配置模型。"""

    test_param: str = "default"


class _TestContextModel(BaseContextModel):
    """测试上下文模型。"""

    temperature: float = 0.5
    max_tokens: int = 100


class _TestTranslationEngine(BaseTranslationEngine[_TestEngineConfig]):
    """用于测试的翻译引擎实现。"""

    CONFIG_MODEL = _TestEngineConfig
    CONTEXT_MODEL = _TestContextModel
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = True
    ACCEPTS_CONTEXT = True

    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """模拟翻译执行，不包含延迟。"""
        await asyncio.sleep(0)  # 允许任务切换
        if "error" not in text:
            return EngineSuccess(
                translated_text=f"{text} (translated to {target_lang})"
            )
        else:
            return EngineError(error_message="Simulated error", is_retryable=True)


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[_TestTranslationEngine, None]:
    """创建测试引擎实例并确保其在测试后关闭。"""
    config = _TestEngineConfig(rpm=600, max_concurrency=5)
    engine = _TestTranslationEngine(config)
    await engine.initialize()
    yield engine
    await engine.close()


@pytest.mark.asyncio
async def test_concurrency_control_limits_active_tasks(
    test_engine: _TestTranslationEngine,
) -> None:
    """
    测试并发控制功能（确定性测试）。
    """
    test_engine.config = _TestEngineConfig(max_concurrency=2)
    test_engine._concurrency_semaphore = asyncio.Semaphore(2)

    active_task_count = 0
    max_concurrent = 0
    task_started_events = [asyncio.Event() for _ in range(5)]
    can_finish_event = asyncio.Event()

    original_execute = test_engine._execute_single_translation

    async def controlled_execute(
        text: str, *args: Any, **kwargs: Any
    ) -> EngineBatchItemResult:
        nonlocal active_task_count, max_concurrent
        task_index = int(text[-1])
        async with asyncio.Lock():
            active_task_count += 1
            max_concurrent = max(max_concurrent, active_task_count)
        task_started_events[task_index].set()
        await can_finish_event.wait()
        async with asyncio.Lock():
            active_task_count -= 1
        return await original_execute(text, *args, **kwargs)

    test_engine._execute_single_translation = controlled_execute  # type: ignore

    tasks = [
        asyncio.create_task(test_engine.atranslate_batch([f"text{i}"], "de", "en"))
        for i in range(5)
    ]

    await asyncio.wait_for(task_started_events[0].wait(), timeout=1)
    await asyncio.wait_for(task_started_events[1].wait(), timeout=1)

    assert max_concurrent == 2
    assert not task_started_events[2].is_set()

    can_finish_event.set()
    await asyncio.gather(*tasks)