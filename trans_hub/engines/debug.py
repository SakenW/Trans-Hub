# trans_hub/engines/debug.py (v1.1)
"""
提供一个用于开发和测试的调试翻译引擎。
此版本修正了其配置读取逻辑和继承关系。
"""
from typing import List, Optional

from pydantic import Field

# 核心修正：导入 BaseSettings 和 SettingsConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

# 导入引擎基类和相关模型
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


# 核心修正：继承自 BaseSettings 和 BaseEngineConfig
class DebugEngineConfig(BaseSettings, BaseEngineConfig):
    """调试引擎的特定配置模型。"""

    # 添加 model_config 以便 pydantic-settings 正常工作
    model_config = SettingsConfigDict(extra="ignore")

    mode: str = Field(default="SUCCESS", description="SUCCESS, FAIL, or PARTIAL_FAIL")
    fail_on_text: Optional[str] = Field(
        default=None, description="如果文本匹配此字符串，则翻译失败"
    )
    fail_is_retryable: bool = Field(default=True, description="失败是否可重试")
    translation_map: dict[str, str] = Field(
        default_factory=dict, description="一个原文到译文的映射"
    )


class DebugEngine(BaseTranslationEngine[DebugEngineConfig]):
    """一个简单的调试翻译引擎实现。"""

    CONFIG_MODEL = DebugEngineConfig
    CONTEXT_MODEL = BaseContextModel
    VERSION = "1.0.2"

    def __init__(self, config: DebugEngineConfig):
        """初始化 DebugEngine 实例。"""
        super().__init__(config)

    def _debug_translate(self, text: str, target_lang: str) -> str:
        """一个模拟翻译的内部辅助方法。"""
        return self.config.translation_map.get(
            text, f"Translated({text}) to {target_lang}"
        )

    def _process_text(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """内部辅助方法，处理单个文本的翻译。"""
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

        return EngineSuccess(translated_text=self._debug_translate(text, target_lang))

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译方法。"""
        return [self._process_text(text, target_lang) for text in texts]

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译方法。"""
        return self.translate_batch(texts, target_lang, source_lang, context)
