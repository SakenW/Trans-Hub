# trans_hub/engines/translators_engine.py
"""提供一个使用 `translators` 库的免费翻译引擎。"""

import asyncio
from typing import Any, Optional

import structlog

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.engines.meta import register_engine_config
from trans_hub.exceptions import APIError
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

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
    VERSION = "2.2.0"  # 版本号提升，因为实现方式有较大变化
    ACCEPTS_CONTEXT = True

    def __init__(self, config: TranslatorsEngineConfig):
        super().__init__(config)
        self.ts_module: Optional[Any] = None
        logger.info(
            "Translators 引擎已配置，将在首次使用时初始化。",
            default_provider=self.config.provider,
        )

    async def _ensure_initialized(self) -> None:
        """确保 translators 模块被加载。"""
        if self.ts_module:
            return

        logger.debug("正在惰性加载 'translators' 库...")
        try:
            import translators as ts

            self.ts_module = ts
            logger.info("'translators' 库加载成功。")
        except ImportError as e:
            raise ImportError(
                "要使用 TranslatorsEngine, 请先安装 'translators' 库: pip install \"trans-hub[translators]\""
            ) from e
        except Exception as e:
            logger.error("加载 'translators' 库时发生严重错误。", error=str(e))
            raise APIError(f"Translators 库初始化失败: {e}") from e

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        await self._ensure_initialized()
        assert self.ts_module is not None

        provider = context_config.get("provider", self.config.provider)

        def _translate_sync() -> str:
            """在线程池中执行的同步翻译函数。"""
            return str(
                self.ts_module.translate_text(
                    query_text=text,
                    translator=provider,
                    from_language=source_lang or "auto",
                    to_language=target_lang,
                )
            )

        try:
            # 将同步阻塞的调用委托给线程池执行
            translated_text = await asyncio.to_thread(_translate_sync)
            return EngineSuccess(translated_text=translated_text)
        except Exception as e:
            logger.warning(
                "Translators 引擎单条翻译出错", provider=provider, error=str(e)
            )
            return EngineError(
                error_message=f"Translators({provider}) Error: {e}",
                is_retryable=True,  # 免费服务通常因网络问题或速率限制而出错，默认为可重试
            )


register_engine_config("translators", TranslatorsEngineConfig)