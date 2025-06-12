"""
trans_hub/engines/debug.py

提供一个用于开发和测试的调试引擎。
"""
from typing import List, Optional

# 这里的导入没有受到文档更新的影响
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineSuccess


class DebugEngineConfig(BaseEngineConfig):
    """调试引擎的特定配置，目前为空。"""
    pass

class DebugEngine(BaseTranslationEngine):
    """
    一个简单的调试翻译引擎。
    它不进行真正的翻译，而是将输入文本进行简单的变换。
    """
    CONFIG_MODEL = DebugEngineConfig
    VERSION = "1.0.0"

    def _debug_translate(self, text: str, target_lang: str) -> str:
        """核心的伪翻译逻辑。"""
        return f"{text[::-1]}-{target_lang}" # 将文本反转并附加上目标语言

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None, # source_lang 和 context 暂不使用
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """同步版本的批量翻译。"""
        results = [
            EngineSuccess(translated_text=self._debug_translate(text, target_lang))
            for text in texts
        ]
        return results

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """异步版本的批量翻译。"""
        return self.translate_batch(texts, target_lang, source_lang, context)