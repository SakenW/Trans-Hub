# tests/unit/test_policies.py
"""
测试处理策略 (Processing Policies) 的单元测试。
v3.0.0 更新：全面重写以测试基于结构化载荷（payload）的处理逻辑。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from trans_hub.config import RetryPolicyConfig, TransHubConfig
from trans_hub.context import ProcessingContext
from trans_hub.core import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationStatus,
)
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.policies import DefaultProcessingPolicy


@pytest.fixture
def mock_config() -> MagicMock:
    """创建一个更精确的、结构完整的 TransHubConfig mock 对象。"""
    mock = MagicMock(spec=TransHubConfig)
    mock_retry_policy = MagicMock(spec=RetryPolicyConfig)
    mock_retry_policy.max_attempts = 2
    mock_retry_policy.initial_backoff = 0.01
    mock_retry_policy.max_backoff = 10.0
    mock.retry_policy = mock_retry_policy
    mock_active_engine_enum = MagicMock()
    mock_active_engine_enum.value = "debug"
    mock.active_engine = mock_active_engine_enum
    mock.source_lang = "en"
    return mock


@pytest.fixture
def mock_handler() -> AsyncMock:
    """创建一个持久化处理器的 mock 对象。"""
    mock = AsyncMock(spec=PersistenceHandler)
    mock.move_to_dlq = AsyncMock()
    return mock


@pytest.fixture
def mock_cache() -> AsyncMock:
    """创建一个缓存对象的 mock。"""
    mock = AsyncMock()
    mock.get_cached_result.return_value = None
    mock.cache_translation_result = AsyncMock()
    return mock


@pytest.fixture
def mock_active_engine() -> AsyncMock:
    """创建一个翻译引擎的 mock 对象。"""
    mock = AsyncMock(spec=BaseTranslationEngine)
    mock.atranslate_batch.return_value = [EngineSuccess(translated_text="mocked")]
    mock.ACCEPTS_CONTEXT = False
    mock.validate_and_parse_context = MagicMock(return_value=MagicMock())
    mock.name = "debug"
    mock.VERSION = "test-ver-1.0"
    return mock


@pytest.fixture
def mock_processing_context(
    mock_config: MagicMock, mock_handler: AsyncMock, mock_cache: AsyncMock
) -> ProcessingContext:
    """创建一个处理上下文的 mock 对象。"""
    return ProcessingContext(
        config=mock_config,
        handler=mock_handler,
        cache=mock_cache,
        rate_limiter=None,
    )


@pytest.fixture
def sample_batch() -> list[ContentItem]:
    """提供一个用于测试的、包含单个任务的批次。"""
    return [
        ContentItem(
            translation_id="uuid-trans-1",
            business_id="biz-123",
            content_id="uuid-content-1",
            context_id="uuid-context-1",
            source_payload={"text": "Hello", "metadata": "do_not_touch"},
            context={"domain": "testing"},
            source_lang="en",
        )
    ]


@pytest.mark.asyncio
async def test_policy_builds_result_correctly_on_success(
    mock_processing_context: ProcessingContext,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
) -> None:
    """测试默认处理策略能否在翻译成功时正确构建 TranslationResult 对象。"""
    mock_active_engine.atranslate_batch.return_value = [
        EngineSuccess(translated_text="Hallo")
    ]
    policy = DefaultProcessingPolicy()

    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.TRANSLATED
    assert result.business_id == "biz-123"
    assert result.original_payload == {"text": "Hello", "metadata": "do_not_touch"}
    assert result.translated_payload == {"text": "Hallo", "metadata": "do_not_touch"}


@pytest.mark.asyncio
async def test_policy_handles_engine_failure(
    mock_processing_context: ProcessingContext,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
) -> None:
    """测试在引擎返回失败时，策略能否正确构建 FAILED 状态的结果。"""
    mock_active_engine.atranslate_batch.return_value = [
        EngineError(error_message="API limit reached", is_retryable=False)
    ]
    policy = DefaultProcessingPolicy()

    results = await policy.process_batch(
        sample_batch, "de", mock_processing_context, mock_active_engine
    )

    assert len(results) == 1
    result = results[0]
    assert result.status == TranslationStatus.FAILED
    assert result.error == "API limit reached"
    assert result.translated_payload is None
    assert result.original_payload == {"text": "Hello", "metadata": "do_not_touch"}


@pytest.mark.asyncio
async def test_policy_passes_none_source_lang_to_engine(
    mock_processing_context: ProcessingContext,
    mock_active_engine: AsyncMock,
) -> None:
    """测试当任务和全局配置均未提供源语言时，策略是否向引擎传递 None。"""
    # GIVEN: 全局配置和任务项都没有 source_lang
    mock_processing_context.config.source_lang = None
    batch_without_lang = [
        ContentItem(
            translation_id="uuid-no-lang-1",
            business_id="biz-no-lang",
            content_id="c-no-lang-1",
            source_payload={"text": "Some text"},
            context=None,
            source_lang=None,
            context_id=None,
        )
    ]
    policy = DefaultProcessingPolicy()

    # WHEN: 处理该批次
    await policy.process_batch(
        batch_without_lang, "de", mock_processing_context, mock_active_engine
    )

    # THEN: 验证引擎被调用时，source_lang 参数是 None
    mock_active_engine.atranslate_batch.assert_awaited_once()
    call_args = mock_active_engine.atranslate_batch.call_args
    assert call_args.kwargs["source_lang"] is None


@pytest.mark.asyncio
async def test_policy_handles_engine_returning_mismatched_results(
    mock_processing_context: ProcessingContext,
    mock_active_engine: AsyncMock,
) -> None:
    """测试当引擎返回数量不匹配的结果时，策略能将批次中所有项标记为失败。"""
    batch = [
        ContentItem(
            translation_id="uuid-1",
            business_id="b-1",
            content_id="c-1",
            source_payload={"text": "text1"},
            context=None,
            source_lang="en",
            context_id=None,
        ),
        ContentItem(
            translation_id="uuid-2",
            business_id="b-2",
            content_id="c-2",
            source_payload={"text": "text2"},
            context=None,
            source_lang="en",
            context_id=None,
        ),
    ]

    mock_active_engine.atranslate_batch.return_value = [
        EngineSuccess(translated_text="mocked")
    ]
    policy = DefaultProcessingPolicy()

    results = await policy.process_batch(
        batch, "de", mock_processing_context, mock_active_engine
    )

    assert len(results) == 2
    for result in results:
        assert result.status == TranslationStatus.FAILED
        assert result.error is not None
        assert "不匹配" in result.error
