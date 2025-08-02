# tests/unit/engines/test_engine_functionality.py
"""
测试翻译引擎的核心功能，包括速率限制、并发控制和翻译执行。
"""

import asyncio
import time
from typing import Any, Optional, Union, AsyncGenerator

import pytest
from pydantic import BaseModel
from trans_hub.engines.base import BaseContextModel, BaseEngineConfig, BaseTranslationEngine
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class TestEngineConfig(BaseEngineConfig):
    """测试引擎配置模型。"""
    test_param: str = "default"


class TestContextModel(BaseContextModel):
    """测试上下文模型。"""
    temperature: float = 0.5
    max_tokens: int = 100


class TestTranslationEngine(BaseTranslationEngine[TestEngineConfig]):
    """用于测试的翻译引擎实现。"""
    CONFIG_MODEL = TestEngineConfig
    CONTEXT_MODEL = TestContextModel
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = True
    ACCEPTS_CONTEXT = True

    async def _execute_single_translation(
        self, text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any]
    ) -> EngineBatchItemResult:
        """模拟翻译执行。"""
        # 模拟翻译延迟
        await asyncio.sleep(0.1)

        # 模拟成功翻译
        if "error" not in text:
            translated = f"{text} (translated to {target_lang})"
            return EngineSuccess(translated_text=translated, from_cache=False)
        # 模拟翻译失败
        else:
            return EngineError(
                error_message="Simulated error in translation",
                is_retryable=True
            )


@pytest.fixture
async def test_engine() -> AsyncGenerator[TestTranslationEngine, None]:
    """创建测试引擎实例。"""
    config = TestEngineConfig(rpm=60, max_concurrency=5)
    engine = TestTranslationEngine(config)
    await engine.initialize()
    yield engine
    await engine.close()


@pytest.mark.asyncio
async def test_engine_initialization(test_engine: TestTranslationEngine) -> None:
    """测试引擎初始化。"""
    assert isinstance(test_engine, TestTranslationEngine)
    assert isinstance(test_engine.config, TestEngineConfig)
    assert test_engine.config.rpm == 60
    assert test_engine.config.max_concurrency == 5
    assert test_engine._rate_limiter is not None
    assert test_engine._concurrency_semaphore is not None


@pytest.mark.asyncio
async def test_rate_limiter(test_engine: TestTranslationEngine) -> None:
    """测试速率限制功能。"""
    # 修改配置以更容易测试速率限制
    test_engine.config = TestEngineConfig(rps=10)  # 每秒10个请求
    test_engine._rate_limiter = RateLimiter(refill_rate=10, capacity=10)

    # 执行11个请求，应该有一个被限流
    start_time = time.time()
    tasks = [
        test_engine._atranslate_one("test", "en", "zh", {})
        for _ in range(11)
    ]
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    # 确保所有请求成功
    assert all(isinstance(res, EngineSuccess) for res in results)
    # 确保执行时间至少为1秒（因为第11个请求需要等待令牌刷新）
    assert end_time - start_time >= 1.0


@pytest.mark.asyncio
async def test_concurrency_control(test_engine: TestTranslationEngine) -> None:
    """测试并发控制功能。"""
    # 修改配置以更容易测试并发控制
    test_engine.config = TestEngineConfig(max_concurrency=2)
    test_engine._concurrency_semaphore = asyncio.Semaphore(2)

    # 执行5个请求，每个需要0.1秒
    start_time = time.time()
    tasks = [
        test_engine._atranslate_one("test", "en", "zh", {})
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)
    end_time = time.time()

    # 确保所有请求成功
    assert all(isinstance(res, EngineSuccess) for res in results)
    # 确保执行时间至少为0.3秒（5个请求，并发度2，需要3批）
    assert end_time - start_time >= 0.3


@pytest.mark.asyncio
async def test_translate_batch(test_engine: TestTranslationEngine) -> None:
    """测试批量翻译功能。"""
    texts = ["hello", "world", "test error"]
    results = await test_engine.atranslate_batch(texts, "zh", "en")

    # 检查结果数量
    assert len(results) == len(texts)
    # 检查成功结果
    result0: Union[EngineSuccess, EngineError] = results[0]
    assert isinstance(result0, EngineSuccess)
    assert result0.translated_text == "hello (translated to zh)"

    result1: Union[EngineSuccess, EngineError] = results[1]
    assert isinstance(result1, EngineSuccess)
    assert result1.translated_text == "world (translated to zh)"

    # 检查失败结果
    result2: Union[EngineSuccess, EngineError] = results[2]
    assert isinstance(result2, EngineError)
    assert result2.error_message == "Simulated error in translation"


@pytest.mark.asyncio
async def test_source_lang_required(test_engine: TestTranslationEngine) -> None:
    """测试源语言必填功能。"""
    texts = ["hello", "world"]
    results = await test_engine.atranslate_batch(texts, "zh")

    # 检查所有结果都是错误
    assert all(isinstance(res, EngineError) for res in results)
    # 通过索引访问并类型窄化
    result0 = results[0]
    assert isinstance(result0, EngineError)
    assert result0.error_message == f"引擎 '{test_engine.__class__.__name__}' 需要提供源语言。"


@pytest.mark.asyncio
async def test_context_validation(test_engine: TestTranslationEngine) -> None:
    """测试上下文验证功能。"""
    # 有效上下文
    valid_context = TestContextModel(temperature=0.7, max_tokens=200)
    result = test_engine.validate_and_parse_context(valid_context.model_dump())
    assert isinstance(result, TestContextModel)
    assert result.temperature == 0.7

    # 无效上下文
    invalid_context = {"invalid_param": "value"}
    result = test_engine.validate_and_parse_context(invalid_context)
    assert isinstance(result, EngineError)
    assert "上下文验证失败" in result.error_message


@pytest.mark.asyncio
async def test_translate_with_context(test_engine: TestTranslationEngine) -> None:
    """测试带上下文的翻译功能。"""
    texts = ["hello"]
    context = TestContextModel(temperature=0.7)
    results = await test_engine.atranslate_batch(texts, "zh", "en", context)

    assert isinstance(results[0], EngineSuccess)
    assert results[0].translated_text == "hello (translated to zh)"