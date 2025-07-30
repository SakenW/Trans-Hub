# tests/unit/test_policies.py
"""测试处理策略 (Processing Policies) 的单元测试。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from trans_hub.config import RetryPolicyConfig, TransHubConfig
from trans_hub.context import ProcessingContext
from trans_hub.interfaces import PersistenceHandler
from trans_hub.policies import DefaultProcessingPolicy
from trans_hub.types import (
    ContentItem,
    EngineSuccess,
    TranslationStatus,
)


@pytest.fixture
def mock_config() -> MagicMock:
    """创建一个更精确的、结构完整的 TransHubConfig mock 对象。"""
    mock = MagicMock(spec=TransHubConfig)

    mock_retry_policy = MagicMock(spec=RetryPolicyConfig)
    mock_retry_policy.max_attempts = 2
    mock_retry_policy.initial_backoff = 0.01
    mock.retry_policy = mock_retry_policy

    mock_active_engine_enum = MagicMock()
    mock_active_engine_enum.value = "debug"
    mock.active_engine = mock_active_engine_enum

    mock.source_lang = "en"
    return mock


@pytest.fixture
def mock_handler() -> AsyncMock:
    mock = AsyncMock(spec=PersistenceHandler)
    mock.get_business_id_for_job.return_value = "biz-123"
    mock.move_to_dlq = AsyncMock()
    return mock


@pytest.fixture
def mock_cache() -> AsyncMock:
    mock = AsyncMock()
    mock.get_cached_result.return_value = None
    mock.cache_translation_result = AsyncMock()
    return mock


@pytest.fixture
def mock_active_engine() -> AsyncMock:
    mock = AsyncMock()
    mock.atranslate_batch.return_value = [EngineSuccess(translated_text="mocked")]
    mock.ACCEPTS_CONTEXT = False
    mock.validate_and_parse_context = MagicMock(return_value=MagicMock())
    mock.VERSION = "test-ver-1.0"
    return mock


@pytest.fixture
def mock_processing_context(
    mock_config: MagicMock, mock_handler: AsyncMock, mock_cache: AsyncMock
) -> ProcessingContext:
    return ProcessingContext(
        config=mock_config,
        handler=mock_handler,
        cache=mock_cache,
        rate_limiter=None,
    )


@pytest.fixture
def sample_batch() -> list[ContentItem]:
    return [
        ContentItem(
            translation_id="uuid-trans-1",
            business_id="biz-123",
            content_id="uuid-content-1",
            context_id="uuid-context-1",
            value="Hello",
            context={"domain": "testing"},
        )
    ]


@pytest.mark.asyncio
async def test_policy_builds_result_correctly(
    mock_processing_context: ProcessingContext,
    mock_active_engine: AsyncMock,
    sample_batch: list[ContentItem],
) -> None:
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
