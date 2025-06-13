"""trans_hub/engines/debug.py (v0.2)

提供一个用于开发和测试的调试翻译引擎。
此版本新增了模拟翻译失败的能力，以便于测试错误处理流程。
"""
from typing import List, Optional

# 导入引擎基类和相关模型
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)

# 导入引擎处理结果类型 (EngineBatchItemResult, EngineError, EngineSuccess)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class DebugEngineConfig(BaseEngineConfig):
    """调试引擎的特定配置模型。"""

    # 新增配置项：指定哪些文本应该模拟翻译失败
    fail_on_text: Optional[str] = None
    # 新增配置项：模拟的失败是否可重试
    fail_is_retryable: bool = True


class DebugEngine(BaseTranslationEngine):
    """一个简单的调试翻译引擎实现。
    此引擎可以配置为在遇到特定文本时模拟翻译失败，
    或者简单地将文本反转并拼接目标语言代码作为“翻译”结果。
    """

    CONFIG_MODEL = DebugEngineConfig
    VERSION = "1.0.1"  # 引擎版本升级

    def __init__(self, config: DebugEngineConfig):
        """
        初始化 DebugEngine 实例。
        保存配置信息，特别是用于模拟失败的文本内容和失败是否可重试的标志。
        """
        super().__init__(config)
        # 从配置中获取模拟失败的文本和重试性标志，并保存到实例属性中
        self.fail_on_text = config.fail_on_text
        self.fail_is_retryable = config.fail_is_retryable

    def _debug_translate(self, text: str, target_lang: str) -> str:
        """
        一个模拟翻译的内部辅助方法。
        简单地将输入文本反转，并附加目标语言代码，作为模拟的翻译结果。
        """
        return f"{text[::-1]}-{target_lang}"

    def _process_text(self, text: str, target_lang: str) -> EngineBatchItemResult:
        """
        内部辅助方法，处理单个文本的翻译。
        根据 `fail_on_text` 配置决定是模拟成功还是模拟失败。
        """
        # 如果配置了 `fail_on_text` 且当前文本匹配，则模拟失败
        if self.fail_on_text and text == self.fail_on_text:
            return EngineError(
                error_message=f"模拟失败：检测到配置的文本 '{text}'",
                is_retryable=self.fail_is_retryable,
            )
        else:
            # 否则，调用内部的模拟翻译方法，返回成功结果
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
        """
        同步批量翻译方法。
        对批次中的每个文本调用内部处理方法，以决定是模拟成功还是失败。
        """
        # 对批次中的每个文本应用 _process_text 方法
        return [self._process_text(text, target_lang) for text in texts]

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """
        异步批量翻译方法。
        此调试引擎的异步版本与同步版本具有相同的逻辑和行为。
        """
        # 直接调用同步版本进行处理
        return self.translate_batch(texts, target_lang, source_lang, context)
