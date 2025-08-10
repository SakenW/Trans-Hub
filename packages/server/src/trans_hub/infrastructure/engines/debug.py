# packages/server/src/trans_hub/infrastructure/engines/debug.py
"""
提供一个用于开发和测试的调试翻译引擎。
"""
from trans_hub_core.types import EngineBatchItemResult, EngineSuccess
from .base import BaseEngineConfig, BaseTranslationEngine

class DebugEngineConfig(BaseEngineConfig):
    pass

class DebugEngine(BaseTranslationEngine[DebugEngineConfig]):
    """一个简单的调试翻译引擎实现。"""
    CONFIG_MODEL = DebugEngineConfig
    
    async def _translate(self, texts: list[str], target_lang: str, source_lang: str) -> list[EngineBatchItemResult]:
        results = []
        for text in texts:
            results.append(EngineSuccess(translated_text=f"Translated({text}) to {target_lang}"))
        return results