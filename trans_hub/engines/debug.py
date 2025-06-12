"""trans_hub/engines/debug.py (v0.2)

提供一个用于开发和测试的调试引擎。
此版本增加了模拟失败的能力。
"""
from typing import List, Optional

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)

# [新] 导入 EngineError
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class DebugEngineConfig(BaseEngineConfig):
    """调试引擎的特定配置。"""

    # [新] 增加一个配置项，用于指定哪些文本应该模拟失败
    fail_on_text: Optional[str] = None
    fail_is_retryable: bool = True


class DebugEngine(BaseTranslationEngine):
    """一个简单的调试翻译引擎。
    此版本可以配置为在遇到特定文本时模拟失败。
    """

    CONFIG_MODEL = DebugEngineConfig
    VERSION = "1.0.1"  # 版本升级

    def __init__(self, config: DebugEngineConfig):
        super().__init__(config)
        # 将配置中的特殊文本保存到实例属性中
        self.fail_on_text = config.fail_on_text
        self.fail_is_retryable = config.fail_is_retryable

    def _debug_translate(self, text: str, target_lang: str) -> str:
        return f"{text[::-1]}-{target_lang}"

    def _process_text(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """[新] 内部辅助方法，处理单个文本，根据配置决定成功或失败。"""
        if self.fail_on_text and text == self.fail_on_text:
            # 如果当前文本是我们配置的“失败文本”
            return EngineError(
                error_message=f"Simulated failure for text: '{text}'",
                is_retryable=self.fail_is_retryable,
            )
        else:
            # 否则，正常翻译
            return EngineSuccess(
                translated_text=self._debug_translate(text, target_lang)
            )

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译，现在会检查是否需要模拟失败。"""
        return [self._process_text(text, target_lang) for text in texts]

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """异步版本，逻辑相同。"""
        return self.translate_batch(texts, target_lang, source_lang, context)
