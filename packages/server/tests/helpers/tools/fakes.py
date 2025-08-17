# packages/server/tests/helpers/tools/fakes.py
"""
提供测试替身 (Test Doubles)，如 FakeEngine, FakeCache 等。
"""
from __future__ import annotations

from typing import Any

from trans_hub.infrastructure.engines.base import BaseTranslationEngine, BaseEngineConfig
from trans_hub_core.types import EngineBatchItemResult, EngineSuccess, EngineError


class FakeEngineConfig(BaseEngineConfig):
    """FakeEngine 的配置模型。"""
    mode: str = "success"
    fail_on_text: str | None = None


class FakeTranslationEngine(BaseTranslationEngine[FakeEngineConfig]):
    """
    一个用于测试的可预测的假翻译引擎。
    """
    CONFIG_MODEL = FakeEngineConfig
    VERSION = "0.1.0-fake"

    async def _translate(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[EngineBatchItemResult]:
        results: list[EngineBatchItemResult] = []
        for text in texts:
            if self.config.mode == "fail" or text == self.config.fail_on_text:
                results.append(EngineError(error_message="Fake engine failed", is_retryable=True))
                continue
            
            results.append(
                EngineSuccess(translated_text=f"Translated('{text}') to {target_lang}")
            )
        return results