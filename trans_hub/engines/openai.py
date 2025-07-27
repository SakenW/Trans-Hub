# trans_hub/engines/openai.py
"""
提供一个使用 OpenAI API 的翻译引擎。
此版本实现已高度简化，仅需实现 _atranslate_one 方法，并支持通过 context 传入 system_prompt。
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
from trans_hub.engines.meta import register_engine_config
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_AsyncOpenAIClient: Optional[type] = None
try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AsyncOpenAI,
        InternalServerError,
        RateLimitError,
    )

    _AsyncOpenAIClient = AsyncOpenAI
except ImportError:
    pass

logger = structlog.get_logger(__name__)


class OpenAIContext(BaseContextModel):
    """OpenAI 引擎的上下文模型。"""

    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):
    """OpenAI 引擎的配置模型。"""

    model_config = SettingsConfigDict(
        env_prefix="TH_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    openai_api_key: SecretStr
    openai_endpoint: HttpUrl = cast(HttpUrl, "https://api.openai.com/v1")
    openai_model: str = "gpt-3.5-turbo"
    openai_temperature: float = 0.1
    default_prompt_template: str = (
        "Translate the following text from {source_lang} to {target_lang}. "
        "Return only the translated text, without any additional explanations or quotes.\n\n"
        'Text to translate: "{text}"'
    )


class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """使用 OpenAI API 的翻译引擎实现。"""

    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext
    VERSION = "2.2.0"
    REQUIRES_SOURCE_LANG = True
    ACCEPTS_CONTEXT = True  # --- 核心能力声明 ---

    def __init__(self, config: OpenAIEngineConfig):
        super().__init__(config)
        if _AsyncOpenAIClient is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请先安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        self.client: AsyncOpenAI = _AsyncOpenAIClient(
            api_key=self.config.openai_api_key.get_secret_value(),
            base_url=str(self.config.openai_endpoint),
        )
        logger.info(
            "OpenAI 引擎初始化成功",
            model=self.config.openai_model,
        )

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本。"""
        final_source_lang = cast(str, source_lang)

        prompt_template = context_config.get(
            "prompt_template", self.config.default_prompt_template
        )
        model = context_config.get("model", self.config.openai_model)
        temperature = context_config.get("temperature", self.config.openai_temperature)
        system_prompt = context_config.get("system_prompt")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        prompt = prompt_template.format(
            text=text, source_lang=final_source_lang, target_lang=target_lang
        )
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=temperature,
                max_tokens=len(text.encode("utf-8")) * 3 + 150,
            )
            translated_text = response.choices[0].message.content or ""
            if not translated_text:
                return EngineError(
                    error_message="API 返回了空内容。", is_retryable=True
                )
            return EngineSuccess(translated_text=translated_text.strip().strip('"'))
        except APIStatusError as e:
            # --- 核心优化：更精准的错误判断 ---
            is_retryable = isinstance(
                e, (RateLimitError, InternalServerError, APIConnectionError)
            )
            logger.error("OpenAI API 调用出错", error=str(e), is_retryable=is_retryable)
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            # 基类会捕获这个异常，但在这里记录更详细的日志是好的实践
            logger.error("OpenAI 引擎发生未知错误", error=str(e), exc_info=True)
            # 重新抛出异常，让基类的 atranslate_batch 来统一处理
            raise e


# 注册引擎配置
register_engine_config("openai", OpenAIEngineConfig)
