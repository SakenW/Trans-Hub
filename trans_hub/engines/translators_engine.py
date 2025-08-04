# trans_hub/engines/translators_engine.py
"""提供一个使用 `translators` 库的免费翻译引擎。"""

import asyncio
from typing import Any, Optional

import structlog

from trans_hub.core.exceptions import APIError
from trans_hub.core.types import EngineBatchItemResult, EngineError, EngineSuccess
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)

# 修复：添加 logger 定义
logger = structlog.get_logger(__name__)


class TranslatorsContextModel(BaseContextModel):
    """Translators 引擎的上下文。"""

    provider: Optional[str] = None


class TranslatorsEngineConfig(BaseEngineConfig):
    """Translators 引擎的配置。"""

    provider: str = "google"


class TranslatorsEngine(BaseTranslationEngine[TranslatorsEngineConfig]):
    """一个使用 `translators` 库的纯异步引擎。"""

    CONFIG_MODEL = TranslatorsEngineConfig
    CONTEXT_MODEL = TranslatorsContextModel
    VERSION = "2.2.1"
    ACCEPTS_CONTEXT = True

    def __init__(self, config: TranslatorsEngineConfig):
        super().__init__(config)
        self.ts_module: Optional[Any] = None
        logger.info("Translators 引擎已配置。", default_provider=self.config.provider)

    async def _ensure_initialized(self) -> None:
        if self.ts_module:
            return
        logger.debug("正在惰性加载 'translators' 库...")
        try:
            import translators as ts

            self.ts_module = ts
            logger.info("'translators' 库加载成功。")
        except ImportError as e:
            raise ImportError(
                "要使用 TranslatorsEngine, 请安装 'translators' 库: "
                '"pip install "trans-hub[translators]"'
            ) from e
        except Exception as e:
            raise APIError(f"Translators 库初始化失败: {e}") from e

    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        await self._ensure_initialized()
        assert self.ts_module is not None
        ts_lib = self.ts_module

        provider = context_config.get("provider", self.config.provider)

        def _translate_sync() -> str:
            return str(
                ts_lib.translate_text(
                    query_text=text,
                    translator=provider,
                    from_language=source_lang or "auto",
                    to_language=target_lang,
                )
            )

        try:
            translated_text = await asyncio.to_thread(_translate_sync)
            return EngineSuccess(translated_text=translated_text)
        except Exception as e:
            return EngineError(
                error_message=f"Translators({provider}) Error: {e}",
                is_retryable=True,
            )
