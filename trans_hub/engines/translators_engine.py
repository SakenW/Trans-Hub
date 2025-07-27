# trans_hub/engines/translators_engine.py
"""
提供一个使用 `translators` 库的免费翻译引擎。
此版本实现了批处理性能优化，并支持通过 context 切换服务商。
"""

import asyncio
from typing import Any, Optional

import structlog

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.engines.meta import register_engine_config
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

try:
    import translators as ts
except ImportError:
    ts = None

logger = structlog.get_logger(__name__)


class TranslatorsContextModel(BaseContextModel):
    """Translators 引擎的上下文，允许动态选择服务商。"""

    provider: Optional[str] = None


class TranslatorsEngineConfig(BaseEngineConfig):
    """Translators 引擎的配置。"""

    provider: str = "google"


class TranslatorsEngine(BaseTranslationEngine[TranslatorsEngineConfig]):
    """一个使用 `translators` 库的纯异步引擎。"""

    CONFIG_MODEL = TranslatorsEngineConfig
    CONTEXT_MODEL = TranslatorsContextModel
    VERSION = "2.1.0"
    ACCEPTS_CONTEXT = True  # --- 核心能力声明 ---

    def __init__(self, config: TranslatorsEngineConfig):
        super().__init__(config)
        if ts is None:
            raise ImportError(
                "要使用 TranslatorsEngine, 请先安装 'translators' 库: pip install \"trans-hub[translators]\""
            )
        logger.info("Translators 引擎初始化成功", default_provider=self.config.provider)

    # --- 核心优化：覆盖 atranslate_batch 以实现高效的批处理 ---
    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """
        [覆盖] 高效地批量翻译文本。

        将整个批次的同步翻译任务一次性提交到线程池，以减少线程切换开销。
        """
        context_config = self._get_context_config(context)
        provider = context_config.get("provider", self.config.provider)

        # 定义一个在独立线程中运行的同步辅助函数
        def _translate_batch_sync() -> list[EngineBatchItemResult]:
            results: list[EngineBatchItemResult] = []
            for text in texts:
                try:
                    translated_text = str(
                        ts.translate_text(
                            query_text=text,
                            translator=provider,
                            from_language=source_lang or "auto",
                            to_language=target_lang,
                        )
                    )
                    results.append(EngineSuccess(translated_text=translated_text))
                except Exception as e:
                    logger.warning(
                        "Translators 引擎单条翻译出错",
                        provider=provider,
                        error=str(e),
                    )
                    results.append(
                        EngineError(
                            error_message=f"Translators({provider}) Error: {e}",
                            is_retryable=True,
                        )
                    )
            return results

        try:
            # 用一次 to_thread 调用执行整个批处理
            return await asyncio.to_thread(_translate_batch_sync)
        except Exception as e:
            # 捕获 to_thread 本身可能抛出的异常
            logger.error("Translators 批处理线程执行失败", error=str(e), exc_info=True)
            return [EngineError(error_message=str(e), is_retryable=True)] * len(texts)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """
        [不再使用] 由于 atranslate_batch 已被覆盖，此方法不会被调用。
        但作为抽象方法的实现，它必须存在。
        """
        # 理论上这里的代码不会被执行，但我们提供一个备用实现以防万一
        provider = context_config.get("provider", self.config.provider)

        def _translate_sync() -> EngineBatchItemResult:
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
                return EngineError(
                    error_message=f"Translators({provider}) Error: {e}",
                    is_retryable=True,
                )

        return await asyncio.to_thread(_translate_sync)


# 注册引擎配置
register_engine_config("translators", TranslatorsEngineConfig)
