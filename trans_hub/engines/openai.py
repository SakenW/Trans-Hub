# trans_hub/engines/openai.py (重构后)
"""提供一个使用 OpenAI API 的翻译引擎。
此版本实现已高度简化，仅需实现 _atranslate_one 方法。
"""
from typing import Any, Optional, cast

import structlog
from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_AsyncOpenAI: Optional[type] = None
try:
    from openai import APIConnectionError, APIError, InternalServerError, RateLimitError
    from openai import AsyncOpenAI as _AsyncOpenAI
except ImportError:
    pass

logger = structlog.get_logger(__name__)


class OpenAIContext(BaseContextModel):
    prompt_template: Optional[str] = None
    # 可以添加更多上下文可覆盖的参数，如 model, temperature
    model: Optional[str] = None
    temperature: Optional[float] = None


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
    VERSION = "2.0.0" # 版本号提升
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
        logger.info("OpenAI 引擎初始化成功", model=self.config.openai_model)

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str], # 在这里 source_lang 必不为 None
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        # 基类已确保 source_lang 存在
        final_source_lang = cast(str, source_lang)

        # 从全局配置和上下文配置中决定最终参数
        prompt_template = context_config.get("prompt_template", self.config.default_prompt_template)
        model = context_config.get("model", self.config.openai_model)
        temperature = context_config.get("temperature", self.config.openai_temperature)

        prompt = prompt_template.format(
            text=text, source_lang=final_source_lang, target_lang=target_lang
        )
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=len(text.encode("utf-8")) * 2 + 100, # 可以考虑也加入配置
            )
            translated_text = response.choices[0].message.content or ""
            if not translated_text:
                return EngineError(error_message="API returned empty content.", is_retryable=True)
            return EngineSuccess(translated_text=translated_text.strip())
        except APIError as e:
            is_retryable = isinstance(e, (RateLimitError, InternalServerError, APIConnectionError))
            logger.error("OpenAI API 调用出错", error=str(e), is_retryable=is_retryable)
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            logger.error("OpenAI 引擎发生未知错误", error=str(e), exc_info=True)
            return EngineError(error_message=str(e), is_retryable=True)