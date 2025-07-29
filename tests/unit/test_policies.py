# tests/unit/test_policies.py
"""
针对 `trans_hub.policies` 的单元测试。
v3.0 更新：完全适配 v3.0 Schema 和新的 ContentItem DTO。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from trans_hub.context import ProcessingContext
from trans_hub.interfaces import PersistenceHandler
from trans_hub.policies import DefaultProcessingPolicy
from trans_hub.types import ContentItem, EngineSuccess, TranslationStatus


# --- 核心修正：恢复所有 fixture 定义 ---
@pytest.fixture
def mock_config() -> MagicMock:
    mock = MagicMock()
    mock.retry_policy.max_attempts = 2
    mock.retry_policy.initial_backoff = 0.01
    mock.source_lang = "en"
    mock.active_engine.value = "debug"
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
        rate_limiter=AsyncMock(),
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
):
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
