# tests/unit/application/test_translation_processor_validation.py
"""
测试 TranslationProcessor 的数量校验功能。
"""

import pytest
from unittest.mock import AsyncMock, Mock

from trans_hub.application.processors import TranslationProcessor
from trans_hub_core.types import EngineSuccess, EngineError, ContentItem, EngineBatchItemResult


class MockTranslationEngine:
    """用于测试的模拟翻译引擎，可以控制返回结果的数量。"""
    
    def __init__(self, results: list[EngineBatchItemResult]):
        self._results = results
    
    def name(self) -> str:
        return "MockEngine"
    
    VERSION = "1.0.0"
    
    async def atranslate_batch(self, texts: list[str], target_lang: str, source_lang: str = "auto") -> list[EngineBatchItemResult]:
        return self._results


class TestTranslationProcessorValidation:
    """测试 TranslationProcessor 的数量校验功能。"""

    @pytest.fixture
    def processor(self):
        """创建 TranslationProcessor 实例。"""
        mock_stream_producer = AsyncMock()
        mock_stream_producer.publish = AsyncMock()
        return TranslationProcessor(
            stream_producer=mock_stream_producer,
            event_stream_name="test_stream"
        )

    @pytest.fixture
    def mock_engine(self):
        """创建模拟的翻译引擎。"""
        engine = Mock()
        engine.atranslate_batch = AsyncMock()
        return engine

    @pytest.fixture
    def mock_uow(self):
        """创建模拟的工作单元。"""
        uow = AsyncMock()
        uow.translations = AsyncMock()
        uow.tm = AsyncMock()
        uow.commit = AsyncMock()
        return uow

    @pytest.mark.asyncio
    async def test_process_batch_success_with_matching_counts(
        self, processor, mock_engine, mock_uow
    ):
        """测试引擎返回数量与输入数量匹配的正常情况。"""
        # 准备测试数据
        valid_items = [
            ContentItem(
                head_id="head1",
                current_rev_id="rev1",
                current_no=0,
                content_id="content1",
                project_id="project1",
                namespace="default",
                source_payload={"text": "Hello"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
            ContentItem(
                head_id="head2",
                current_rev_id="rev2",
                current_no=0,
                content_id="content2",
                project_id="project1",
                namespace="default",
                source_payload={"text": "World"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
        ]
        
        # 创建引擎 - 返回与输入数量匹配的结果
        engine_results = [
            EngineSuccess(translated_text="你好"),
            EngineSuccess(translated_text="世界")
        ]
        engine = MockTranslationEngine(engine_results)
        
        # 模拟其他依赖
        mock_uow.translations.create_revision = AsyncMock(return_value="rev_123")
        mock_uow.tm.upsert_entry = AsyncMock(return_value="tm_123")
        mock_uow.tm.link_revision_to_tm = AsyncMock()
        
        # 执行测试
        await processor.process_batch(
            uow=mock_uow,
            batch=valid_items,
            active_engine=engine
        )
        
        # 验证成功处理 - 检查是否调用了相关的 UoW 方法
        mock_uow.translations.create_revision.assert_called()
        mock_uow.tm.upsert_entry.assert_called()
        mock_uow.tm.link_revision_to_tm.assert_called()

    @pytest.mark.asyncio
    async def test_process_batch_fails_with_fewer_outputs(
        self, processor, mock_engine, mock_uow
    ):
        """测试引擎返回数量少于输入数量的异常情况。"""
        # 准备测试数据
        valid_items = [
            ContentItem(
                head_id="head1",
                current_rev_id="rev1",
                current_no=0,
                content_id="content1",
                project_id="project1",
                namespace="default",
                source_payload={"text": "Hello"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
            ContentItem(
                head_id="head2",
                current_rev_id="rev2",
                current_no=0,
                content_id="content2",
                project_id="project1",
                namespace="default",
                source_payload={"text": "World"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),

        ]
        
        # 创建引擎 - 返回数量少于输入的结果
        engine_results = [
            EngineSuccess(translated_text="你好")
            # 故意只返回一个结果，而输入有两个
        ]
        engine = MockTranslationEngine(engine_results)
        
        # 执行测试并验证异常
        with pytest.raises(ValueError) as exc_info:
            await processor.process_batch(
                uow=mock_uow,
                batch=valid_items,
                active_engine=engine
            )
        
        # 验证异常消息
        assert "引擎返回结果数量不匹配" in str(exc_info.value)
        assert "期望 2 个结果" in str(exc_info.value)
        assert "实际收到 1 个结果" in str(exc_info.value)
        
        # 验证没有提交
        mock_uow.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_batch_fails_with_more_outputs(
        self, processor, mock_engine, mock_uow
    ):
        """测试引擎返回数量多于输入数量的异常情况。"""
        # 准备测试数据
        valid_items = [
            ContentItem(
                head_id="head1",
                current_rev_id="rev1",
                current_no=0,
                content_id="content1",
                project_id="project1",
                namespace="default",
                source_payload={"text": "Hello"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
            ContentItem(
                head_id="head2",
                current_rev_id="rev2",
                current_no=0,
                content_id="content2",
                project_id="project1",
                namespace="default",
                source_payload={"text": "World"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
        ]
        
        # 创建引擎 - 返回数量多于输入的结果
        engine_results = [
            EngineSuccess(translated_text="你好"),
            EngineSuccess(translated_text="世界"),
            EngineSuccess(translated_text="额外结果")
            # 故意返回三个结果，而输入只有两个
        ]
        engine = MockTranslationEngine(engine_results)
        
        # 执行测试并验证异常
        with pytest.raises(ValueError) as exc_info:
            await processor.process_batch(
                uow=mock_uow,
                batch=valid_items,
                active_engine=engine
            )
        
        # 验证异常消息
        assert "引擎返回结果数量不匹配" in str(exc_info.value)
        assert "期望 2 个结果" in str(exc_info.value)
        assert "实际收到 3 个结果" in str(exc_info.value)
        
        # 验证没有提交
        mock_uow.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_batch_fails_with_empty_outputs(
        self, processor, mock_engine, mock_uow
    ):
        """测试引擎返回空结果的异常情况。"""
        # 准备测试数据
        valid_items = [
            ContentItem(
                head_id="head1",
                current_rev_id="rev1",
                current_no=0,
                content_id="content1",
                project_id="project1",
                namespace="default",
                source_payload={"text": "Hello"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
        ]
        
        # 创建引擎 - 返回空结果
        engine_results = []
        engine = MockTranslationEngine(engine_results)
        
        # 执行测试并验证异常
        with pytest.raises(ValueError) as exc_info:
            await processor.process_batch(
                uow=mock_uow,
                batch=valid_items,
                active_engine=engine
            )
        
        # 验证异常消息
        assert "引擎返回结果数量不匹配" in str(exc_info.value)
        assert "期望 1 个结果" in str(exc_info.value)
        assert "实际收到 0 个结果" in str(exc_info.value)
        
        # 验证没有提交
        mock_uow.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_batch_with_mixed_success_error_results(
        self, processor, mock_engine, mock_uow
    ):
        """测试引擎返回混合成功和错误结果的正常情况。"""
        # 准备测试数据
        valid_items = [
            ContentItem(
                head_id="head1",
                current_rev_id="rev1",
                current_no=0,
                content_id="content1",
                project_id="project1",
                namespace="default",
                source_payload={"text": "Hello"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),
            ContentItem(
                head_id="head2",
                current_rev_id="rev2",
                current_no=0,
                content_id="content2",
                project_id="project1",
                namespace="default",
                source_payload={"text": "World"},
                source_lang="en",
                target_lang="zh",
                variant_key="-"
            ),

        ]
        
        # 创建引擎 - 返回混合成功和错误结果
        engine_results = [
            EngineSuccess(translated_text="你好"),
            EngineError(error_message="翻译失败", is_retryable=True)
        ]
        engine = MockTranslationEngine(engine_results)
        
        # 模拟其他依赖
        mock_uow.translations.create_revision = AsyncMock(return_value="rev_123")
        mock_uow.tm.upsert_entry = AsyncMock(return_value="tm_123")
        mock_uow.tm.link_revision_to_tm = AsyncMock()
        
        # 执行测试
        await processor.process_batch(
            uow=mock_uow,
            batch=valid_items,
            active_engine=engine
        )
        
        # 验证结果 - 即使有错误结果，只要数量匹配就不应该抛出数量校验异常
        # 成功的条目应该被处理
        mock_uow.translations.create_revision.assert_called_once()
        mock_uow.tm.upsert_entry.assert_called_once()
        mock_uow.tm.link_revision_to_tm.assert_called_once()