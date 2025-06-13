"""trans_hub/engines/translators_engine.py

提供一个使用 `translators` 库的免费翻译引擎。
"""
from typing import List, Optional

# 使用 try-except 来处理可选依赖
try:
    import translators as ts
except ImportError:
    ts = None

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class TranslatorsEngineConfig(BaseEngineConfig):
    """translators 引擎的配置。"""

    # 允许用户指定优先使用的翻译服务，如 'google', 'bing'
    provider: str = "google"


class TranslatorsEngine(BaseTranslationEngine):
    """一个使用 `translators` 库提供免费翻译的引擎。
    这是一个很好的默认或备用引擎，因为它无需 API Key。
    """

    CONFIG_MODEL = TranslatorsEngineConfig
    VERSION = "1.0.0"

    def __init__(self, config: TranslatorsEngineConfig):
        """初始化 TranslatorsEngine，设置翻译服务提供商。"""
        super().__init__(config)
        if ts is None:
            raise ImportError(
                "要使用 TranslatorsEngine，请先安装 'translators' 库: pip install translators"
            )
        self.provider = self.config.provider

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """
        批量翻译文本内容。

        使用指定的翻译服务将输入文本列表翻译为目标语言。
        若未提供源语言，默认自动检测。

        参数:
            texts (List[str]): 需要翻译的文本列表。
            target_lang (str): 目标语言代码，例如 'en' 或 'zh-CN'。
            source_lang (Optional[str]): 源语言代码，默认为自动检测。
            context (Optional[BaseContextModel]): 上下文信息，当前未使用。

        返回:
            List[EngineBatchItemResult]: 包含翻译结果或错误信息的结果列表。
        """
        results: List[EngineBatchItemResult] = []
        for text in texts:
            try:
                # 调用 translators 库
                # 注意：某些语言代码可能需要映射，例如 'zh-CN' -> 'zh-CN'
                translated_text = ts.translate_text(
                    query_text=text,
                    translator=self.provider,
                    from_language=source_lang or "auto",
                    to_language=target_lang,
                )
                results.append(EngineSuccess(translated_text=translated_text))
            except Exception as e:
                # translators 库的错误通常是临时的，我们将其标记为可重试
                results.append(
                    EngineError(
                        error_message=f"Translators lib error: {e}", is_retryable=True
                    )
                )
        return results

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: str,
        context: Optional[BaseContextModel] = None,  # context 可以设为可选参数
    ) -> List[EngineBatchItemResult]:
        """异步版本的 translate_batch，当前使用同步实现包装。"""
        # translators 库也支持异步，但我们 v1.0 暂时保持同步实现
        return self.translate_batch(texts, target_lang, source_lang, context)
