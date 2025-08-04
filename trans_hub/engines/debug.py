# trans_hub/engines/debug.py
"""提供一个用于开发和测试的调试翻译引擎。"""

from typing import Any, Dict, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from trans_hub.core.types import EngineBatchItemResult, EngineError, EngineSuccess
from trans_hub.engines.base import BaseEngineConfig, BaseTranslationEngine


class DebugEngineConfig(BaseSettings, BaseEngineConfig):
    """Debug 引擎的配置模型。"""

    mode: str = Field(default="SUCCESS", description="SUCCESS, FAIL, or PARTIAL_FAIL")
    fail_on_text: Optional[str] = Field(default=None)
    fail_is_retryable: bool = Field(default=True)
    translation_map: Dict[str, str] = Field(default_factory=dict)


class DebugEngine(BaseTranslationEngine[DebugEngineConfig]):
    """一个简单的调试翻译引擎实现。"""

    CONFIG_MODEL = DebugEngineConfig
    VERSION = "2.1.0"

    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        if self.config.mode == "FAIL":
            return EngineError(
                error_message="DebugEngine is in FAIL mode.",
                is_retryable=self.config.fail_is_retryable,
            )

        if self.config.fail_on_text and text == self.config.fail_on_text:
            return EngineError(
                error_message=f"模拟失败：检测到配置的文本 '{text}'",
                is_retryable=self.config.fail_is_retryable,
            )

        translated_text = self.config.translation_map.get(
            text, f"Translated({text}) to {target_lang}"
        )
        return EngineSuccess(translated_text=translated_text)
