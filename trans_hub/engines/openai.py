# trans_hub/engines/openai.py (Mypy 最终修复版)
import asyncio
from typing import Optional, cast

import structlog
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# --- 核心修正：使用 _AsyncOpenAI 变量来持有类型 ---
_AsyncOpenAI: Optional[type] = None
try:
    from openai import (
        APIConnectionError,
        APIError,
        InternalServerError,
        RateLimitError,
    )
    from openai import (
        AsyncOpenAI as _AsyncOpenAI,
    )
except ImportError:
    pass  # 保持 _AsyncOpenAI 为 None

logger = structlog.get_logger(__name__)


class OpenAIContext(BaseContextModel):
    prompt_template: Optional[str] = None


class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):
    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    openai_api_key: SecretStr
    openai_endpoint: HttpUrl = cast(HttpUrl, "https://api.openai.com/v1")
    openai_model: str = "gpt-3.5-turbo"
    openai_temperature: float = 0.1
    default_prompt_template: str = (
        "You are a professional translation engine. Please translate the following text from {source_lang} to {target_lang}. "
        "Only return the translated text, without any additional explanations or superfluous quotes.\n\n"
        'Text to translate: "{text}"'
    )


class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext
    VERSION = "1.2.0"
    REQUIRES_SOURCE_LANG = True

    def __init__(self, config: OpenAIEngineConfig):
        super().__init__(config)
        if _AsyncOpenAI is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请先安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        self.client = _AsyncOpenAI(
            api_key=self.config.openai_api_key.get_secret_value(),
            base_url=str(self.config.openai_endpoint),
        )
        logger.info(
            "OpenAI 引擎初始化成功",
            model=self.config.openai_model,
            endpoint=str(self.config.openai_endpoint),
        )

    async def _translate_single_text(
        self, text: str, target_lang: str, source_lang: str, prompt_template: str
    ) -> EngineBatchItemResult:
        prompt = prompt_template.format(
            text=text, source_lang=source_lang, target_lang=target_lang
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.openai_temperature,
                max_tokens=len(text.encode("utf-8")) * 2 + 100,
            )
            translated_text = response.choices[0].message.content or ""
            if not translated_text:
                return EngineError(
                    error_message="API returned empty content.", is_retryable=True
                )
            return EngineSuccess(translated_text=translated_text.strip())
        except APIError as e:
            is_retryable = isinstance(
                e, (RateLimitError, InternalServerError, APIConnectionError)
            )
            logger.error("OpenAI API 调用出错", error=str(e), is_retryable=is_retryable)
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            logger.error("OpenAI 引擎发生未知错误", error=str(e), exc_info=True)
            return EngineError(error_message=str(e), is_retryable=True)

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        if not source_lang:
            return [
                EngineError(
                    error_message="OpenAI engine requires a source language.",
                    is_retryable=False,
                )
            ] * len(texts)

        prompt_template = self.config.default_prompt_template
        if isinstance(context, OpenAIContext) and context.prompt_template:
            prompt_template = context.prompt_template

        tasks = [
            self._translate_single_text(text, target_lang, source_lang, prompt_template)
            for text in texts
        ]
        results = await asyncio.gather(*tasks)
        return list(results)
