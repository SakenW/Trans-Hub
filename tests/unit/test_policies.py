# tests/unit/test_policies.py
"""
针对 `trans_hub.policies` 的单元测试。

这些测试是独立的，不依赖于真实的数据库或网络连接。
它们通过模拟（Mocking）依赖项，精确地验证处理策略的内部逻辑，
如重试、缓存、上下文处理等。
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
def mock_processing_context() -> MagicMock:
    """提供一个包含了所有被模拟的依赖项的 ProcessingContext Mock。"""
    mock_engine = AsyncMock()
    mock_engine.atranslate_batch.return_value = [
        EngineSuccess(translated_text="mocked")
    ]
    mock_engine.ACCEPTS_CONTEXT = False
    # --- 关键修正：这是一个同步方法，必须使用 MagicMock ---
    mock_engine.validate_and_parse_context = MagicMock(return_value=MagicMock())

    mock_rate_limiter = AsyncMock()

    mock_config = MagicMock()
    mock_config.retry_policy.max_attempts = 2
    mock_config.retry_policy.initial_backoff = 0.01
    mock_config.source_lang = "en"
    mock_config.active_engine = "debug"

    mock_handler = AsyncMock()
    mock_handler.get_business_id_for_content.return_value = "biz-123"

    mock_cache = AsyncMock()
    mock_cache.get_cached_result.return_value = None

    mock_context = MagicMock(spec=ProcessingContext)
    mock_context.config = mock_config
    mock_context.handler = mock_handler
    mock_context.cache = mock_cache
    mock_context.rate_limiter = mock_rate_limiter
    type(mock_context).active_engine = property(fget=lambda self: mock_engine)

    return mock_context


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
async def test_policy_skips_context_for_unsupported_engine(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem]
):
    """测试：当引擎不支持上下文时，策略是否会跳过上下文验证。"""
    mock_engine = mock_processing_context.active_engine
    mock_engine.ACCEPTS_CONTEXT = False
    mock_engine.validate_and_parse_context = MagicMock()

    policy = DefaultProcessingPolicy()
    await policy.process_batch(sample_batch, "de", mock_processing_context)

    mock_engine.validate_and_parse_context.assert_not_called()
    mock_engine.atranslate_batch.assert_called_once_with(
        texts=[item.value for item in sample_batch],
        target_lang="de",
        source_lang=mock_processing_context.config.source_lang,
        context=None,
    )


@pytest.mark.asyncio
async def test_policy_uses_context_for_supported_engine(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem]
):
    """测试：当引擎支持上下文时，策略是否会正确地验证和传递上下文。"""
    mock_engine = mock_processing_context.active_engine
    mock_engine.ACCEPTS_CONTEXT = True
    mock_parsed_context = MagicMock()
    mock_engine.validate_and_parse_context.return_value = mock_parsed_context

    policy = DefaultProcessingPolicy()
    await policy.process_batch(sample_batch, "de", mock_processing_context)

    mock_engine.validate_and_parse_context.assert_called_once_with(
        sample_batch[0].context
    )
    mock_engine.atranslate_batch.assert_called_once_with(
        texts=[item.value for item in sample_batch],
        target_lang="de",
        source_lang=mock_processing_context.config.source_lang,
        context=mock_parsed_context,
    )


@pytest.mark.asyncio
async def test_policy_handles_invalid_context(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem]
):
    """测试：当上下文验证失败时，策略是否能正确处理并返回失败结果。"""
    mock_engine = mock_processing_context.active_engine
    mock_engine.ACCEPTS_CONTEXT = True
    context_error = EngineError(error_message="Invalid context", is_retryable=False)
    mock_engine.validate_and_parse_context.return_value = context_error

    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(sample_batch, "de", mock_processing_context)

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.FAILED
    assert result.error == "Invalid context"
    mock_engine.atranslate_batch.assert_not_called()


@pytest.mark.asyncio
async def test_policy_uses_cache_and_skips_translation(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem]
):
    """测试：当缓存命中时，策略是否直接使用缓存结果，而不调用翻译引擎。"""
    mock_cache = mock_processing_context.cache
    mock_cache.get_cached_result.return_value = "Cached Hello"

    mock_engine = mock_processing_context.active_engine
    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(sample_batch, "de", mock_processing_context)

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.translated_content == "Cached Hello"
    assert result.from_cache is True
    mock_engine.atranslate_batch.assert_not_called()


@pytest.mark.asyncio
async def test_policy_retry_logic_on_retryable_error(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem], monkeypatch
):
    """测试：当引擎返回可重试错误时，策略是否会执行重试。"""
    mock_engine = mock_processing_context.active_engine
    retryable_error = EngineError(error_message="Rate limit", is_retryable=True)
    success_result = EngineSuccess(translated_text="Success after retry")
    mock_engine.atranslate_batch.side_effect = [[retryable_error], [success_result]]

    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(sample_batch, "de", mock_processing_context)

    assert len(results) == 1
    assert results[0].status == TranslationStatus.TRANSLATED
    assert results[0].translated_content == "Success after retry"
    assert mock_engine.atranslate_batch.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_policy_no_retry_on_non_retryable_error(
    mock_processing_context: MagicMock, sample_batch: list[ContentItem], monkeypatch
):
    """测试：当引擎返回不可重试错误时，策略是否会立即失败，不进行重试。"""
    mock_engine = mock_processing_context.active_engine
    non_retryable_error = EngineError(
        error_message="Invalid API Key", is_retryable=False
    )
    mock_engine.atranslate_batch.return_value = [non_retryable_error]

    mock_sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    policy = DefaultProcessingPolicy()
    results = await policy.process_batch(sample_batch, "de", mock_processing_context)

    assert len(results) == 1
    assert results[0].status == TranslationStatus.FAILED
    assert results[0].error == "Invalid API Key"
    mock_engine.atranslate_batch.assert_called_once()
    mock_sleep.assert_not_called()


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])
