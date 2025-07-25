# trans_hub/engines/debug.py (重构后)
"""提供一个用于开发和测试的调试翻译引擎。
此版本实现已高度简化，仅需实现 _atranslate_one 方法。
"""
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class DebugEngineConfig(BaseSettings, BaseEngineConfig):
    model_config = SettingsConfigDict(extra="ignore")
    mode: str = Field(default="SUCCESS", description="SUCCESS, FAIL, or PARTIAL_FAIL")
    fail_on_text: Optional[str] = Field(default=None, description="如果文本匹配此字符串，则翻译失败")
    fail_is_retryable: bool = Field(default=True, description="失败是否可重试")
    translation_map: dict[str, str] = Field(default_factory=dict, description="一个原文到译文的映射")


class DebugEngine(BaseTranslationEngine[DebugEngineConfig]):
    """一个简单的调试翻译引擎实现。"""

    CONFIG_MODEL = DebugEngineConfig
    CONTEXT_MODEL = BaseContextModel
    VERSION = "2.0.0" # 版本号提升

    def __init__(self, config: DebugEngineConfig):
        super().__init__(config)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        # Debug 引擎的模式不受上下文影响，但可以按需添加
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