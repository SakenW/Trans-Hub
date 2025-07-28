# tests/unit/test_policies.py
"""
针对 `trans_hub.policies` 的单元测试。

这些测试是独立的，不依赖于真实的数据库或网络连接。
它们通过模拟（Mocking）依赖项，精确地验证处理策略的内部逻辑，
如重试、缓存、上下文处理以及死信队列（DLQ）行为。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from trans_hub.context import ProcessingContext
from trans_hub.policies import DefaultProcessingPolicy
from trans_hub.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationStatus,
)


@pytest.fixture
def mock_config() -> MagicMock:
    """提供一个模拟的配置对象。"""
    mock = MagicMock()
    mock.retry_policy.max_attempts = 2
    mock.retry_policy.initial_backoff = 0.01
    mock.source_lang = "en"
    mock.active_engine.value = "debug"
    return mock


@pytest.fixture
def mock_handler() -> AsyncMock:
    """提供一个模拟的持久化处理器。"""
    mock = AsyncMock()
    mock.get_business_id_for_content.return_value = "biz-123"
    mock.move_to_dlq = AsyncMock()
    return mock


@pytest.fixture
def mock_cache() -> AsyncMock:
    """提供一个模拟的缓存对象。"""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_translation_result = AsyncMock()
    return mock


@pytest.fixture
def mock_active_engine() -> AsyncMock:
    """提供一个模拟的活动翻译引擎。"""
    mock = AsyncMock()
    mock.atranslate_batch.return_value = [EngineSuccess(translated_text="mocked")]
    mock.ACCEPTS_CONTEXT = False
    mock.validate_and_parse_context = MagicMock(return_value=MagicMock())
    mock.VERSION = "test-ver-1.0"
    return mock


@pytest.fixture
def mock_processing_context(
    mock_config: MagicMock, mock_handler: AsyncMock, mock_cache: AsyncMock
) -> MagicMock:
    """
    提供一个完全被模拟的 ProcessingContext 对象。
    这解决了 mypy 对真实类实例进行动态属性修改的抱怨。
    """
    # --- 核心修正：返回一个 MagicMock，而不是真实的 ProcessingContext ---
    mock = MagicMock(spec=ProcessingContext)
    mock.config = mock_config
    mock.handler = mock_handler
    mock.cache = mock_cache
    mock.rate_limiter = AsyncMock()
    return mock


@pytest.fixture
def sample_batch() -> list[ContentItem]:
    """提供一个简单的待翻译批次。"""
    return [
        ContentItem(
            content_id=1,
            value="Hello",
            context_hash="hash1",
            context={"lang": "en"},
        )
    ]


@pytest.mark.asyncio
async def test_policy_uses_cache_and_skips_translation(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
):
    """测试：当缓存命中时，策略是否直接使用缓存结果，而不调用翻译引擎。"""
    mock_processing_context.cache.get_cached_result.return_value = "Cached Hello"

    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == "Cached Hello"
    assert result.from_cache is True
    mock_active_engine.atranslate_batch.assert_not_called()


@pytest.mark.asyncio
async def test_policy_moves_to_dlq_after_max_retries(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
    monkeypatch,
):
    """
    测试：当任务达到最大重试次数后，是否会被移入死信队列，
    并且不会作为 TranslationResult 返回。
    """
    retryable_error = EngineError(error_message="Persistent error", is_retryable=True)
    mock_active_engine.atranslate_batch.return_value = [retryable_error]
    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    mock_handler = mock_processing_context.handler

    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )

    assert len(results) == 0
    assert mock_active_engine.atranslate_batch.call_count == 3
    assert mock_sleep.call_count == 2

    mock_handler.move_to_dlq.assert_called_once()
    dlq_call_args = mock_handler.move_to_dlq.call_args
    assert dlq_call_args.kwargs["item"] == sample_batch[0]
    assert dlq_call_args.kwargs["error_message"] == "达到最大重试次数"
    assert dlq_call_args.kwargs["engine_name"] == "debug"
    assert dlq_call_args.kwargs["engine_version"] == "test-ver-1.0"


# --- 其他未修改的测试用例 ... ---


@pytest.mark.asyncio
async def test_policy_skips_context_for_unsupported_engine(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
):
    mock_active_engine.ACCEPTS_CONTEXT = False
    mock_active_engine.validate_and_parse_context = MagicMock()
    policy = DefaultProcessingPolicy()
    await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )
    mock_active_engine.validate_and_parse_context.assert_not_called()
    mock_active_engine.atranslate_batch.assert_called_once_with(
        texts=[item.value for item in sample_batch],
        target_lang="de",
        source_lang=mock_processing_context.config.source_lang,
        context=None,
    )


@pytest.mark.asyncio
async def test_policy_uses_context_for_supported_engine(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
):
    mock_active_engine.ACCEPTS_CONTEXT = True
    mock_parsed_context = MagicMock()
    mock_active_engine.validate_and_parse_context.return_value = mock_parsed_context
    policy = DefaultProcessingPolicy()
    await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )
    mock_active_engine.validate_and_parse_context.assert_called_once_with(
        sample_batch[0].context
    )
    mock_active_engine.atranslate_batch.assert_called_once_with(
        texts=[item.value for item in sample_batch],
        target_lang="de",
        source_lang=mock_processing_context.config.source_lang,
        context=mock_parsed_context,
    )


@pytest.mark.asyncio
async def test_policy_handles_invalid_context(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
):
    mock_active_engine.ACCEPTS_CONTEXT = True
    context_error = EngineError(error_message="Invalid context", is_retryable=False)
    mock_active_engine.validate_and_parse_context.return_value = context_error
    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )
    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.FAILED
    assert result.error == "Invalid context"
    mock_active_engine.atranslate_batch.assert_not_called()


@pytest.mark.asyncio
async def test_policy_retry_logic_on_retryable_error(
    mock_processing_context: MagicMock,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
    monkeypatch,
):
    retryable_error = EngineError(error_message="Rate limit", is_retryable=True)
    success_result = EngineSuccess(translated_text="Success after retry")
    mock_active_engine.atranslate_batch.side_effect = [
        [retryable_error],
        [success_result],
    ]
    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )
    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED
    assert results[0].translated_content == "Success after retry"
    assert mock_active_engine.atranslate_batch.call_count == 2
    mock_sleep.assert_called_once()
