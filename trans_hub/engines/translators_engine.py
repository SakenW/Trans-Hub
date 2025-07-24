# trans_hub/engines/translators_engine.py

"""提供一个使用 `translators` 库的免费翻译引擎。
此版本为纯异步设计，并使用 asyncio.to_thread 包装同步调用。.
"""

import asyncio
from typing import Optional

import structlog

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

try:
    import translators as ts
except ImportError:
    ts = None

logger = structlog.get_logger(__name__)


class TranslatorsContextModel(BaseContextModel):
    """Translators 引擎的上下文，允许动态选择服务商。."""

    provider: Optional[str] = None


class TranslatorsEngineConfig(BaseEngineConfig):
    """Translators 引擎的配置。."""

    provider: str = "google"


class TranslatorsEngine(BaseTranslationEngine[TranslatorsEngineConfig]):
    """一个使用 `translators` 库的纯异步引擎。."""

    CONFIG_MODEL = TranslatorsEngineConfig
    CONTEXT_MODEL = TranslatorsContextModel
    VERSION = "1.1.0"

    def __init__(self, config: TranslatorsEngineConfig):
        super().__init__(config)
        if ts is None:
            raise ImportError(
                "要使用 TranslatorsEngine, 请先安装 'translators' 库: pip install \"trans-hub[translators]\""
            )
        self.provider = self.config.provider
        logger.info("Translators 引擎初始化成功", default_provider=self.provider)

    def _translate_single_sync(
        self, text: str, target_lang: str, source_lang: Optional[str], provider: str
    ) -> EngineBatchItemResult:
        """[私有] 同步翻译单个文本的辅助方法。
        这个方法将在一个单独的线程中被调用。.
        """
        try:
            # 确保 ts.translate_text 的结果是字符串
            translated_text = str(
                ts.translate_text(
                    query_text=text,
                    translator=provider,
                    from_language=source_lang or "auto",
                    to_language=target_lang,
                )
            )
            return EngineSuccess(translated_text=translated_text)
        except Exception as e:
            logger.error(
                "Translators 引擎翻译出错",
                text_preview=text[:30],
                error=str(e),
                exc_info=True,
            )
            return EngineError(
                error_message=f"Translators 库错误: {e}", is_retryable=True
            )

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """[异步] 批量翻译。通过 asyncio.to_thread 并发执行同步的翻译调用。."""
        provider = self.provider
        if isinstance(context, TranslatorsContextModel) and context.provider:
            provider = context.provider

        tasks = [
            asyncio.to_thread(
                self._translate_single_sync, text, target_lang, source_lang, provider
            )
            for text in texts
        ]
        results = await asyncio.gather(*tasks)
        return list(results)
