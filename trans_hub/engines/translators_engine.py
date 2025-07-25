# trans_hub/engines/translators_engine.py (重构后)
"""提供一个使用 `translators` 库的免费翻译引擎。
此版本实现已高度简化，仅需实现 _atranslate_one 方法。
"""

import asyncio
from typing import Any, Optional

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
    """一个使用 `translators` 库的纯异步引擎。"""

    CONFIG_MODEL = TranslatorsEngineConfig
    CONTEXT_MODEL = TranslatorsContextModel
    VERSION = "2.0.0" # 版本号提升

    def __init__(self, config: TranslatorsEngineConfig):
        super().__init__(config)
        if ts is None:
            raise ImportError(
                "要使用 TranslatorsEngine, 请先安装 'translators' 库: pip install \"trans-hub[translators]\""
            )
        logger.info("Translators 引擎初始化成功", default_provider=self.config.provider)

    def _translate_single_sync(
        self, text: str, target_lang: str, source_lang: Optional[str], provider: str
    ) -> EngineBatchItemResult:
        """[私有] 同步翻译单个文本的辅助方法。将在一个单独的线程中被调用。"""
        try:
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
                provider=provider,
                error=str(e),
                exc_info=True,
            )
            return EngineError(error_message=f"Translators({provider}) Error: {e}", is_retryable=True)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        # 从全局配置和上下文配置中决定最终的 provider
        provider = context_config.get("provider", self.config.provider)

        # 将同步的阻塞调用放到单独的线程中执行
        return await asyncio.to_thread(
            self._translate_single_sync, text, target_lang, source_lang, provider
        )