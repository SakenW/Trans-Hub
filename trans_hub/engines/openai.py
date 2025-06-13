"""trans_hub/engines/openai.py (v1.0 Final)

提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
实现了从 .env 主动加载配置的最佳实践，并支持异步翻译。
"""
import logging
from typing import List, Optional

import openai
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict  # 确保 BaseSettings 导入

# 核心修复：从 base 模块中导入 BaseEngineConfig
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

logger = logging.getLogger(__name__)


# 核心修复：OpenAIEngineConfig 同时继承 BaseSettings 和 BaseEngineConfig
class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):  # <--- 这一行是关键修改
    """OpenAI 引擎的特定配置。
    通过 pydantic-settings 从环境变量中加载配置，并继承通用引擎配置。
    """

    model_config = SettingsConfigDict(
        # 不再需要 env_prefix，因为 validation_alias 提供了完整的变量名
        # 不再需要 env_file，因为我们将通过 dotenv 主动加载
        extra="ignore"
    )

    api_key: Optional[str] = Field(default=None, validation_alias="TH_OPENAI_API_KEY")
    base_url: Optional[str] = Field(default=None, validation_alias="TH_OPENAI_ENDPOINT")
    model: str = Field(default="gpt-3.5-turbo", validation_alias="TH_OPENAI_MODEL")

    prompt_template: str = (
        "You are a professional translation engine. "
        "Translate the following text from {source_lang} to {target_lang}. "
        "Do not output any other text, explanation, or notes. "
        "Just return the translated text.\n\n"
        'Text to translate: "{text}"'
    )
    default_source_lang: str = "auto"


class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """一个使用 OpenAI (GPT) 进行翻译的引擎。
    此引擎主要设计为异步操作。
    """

    CONFIG_MODEL = OpenAIEngineConfig
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = False

    def __init__(self, config: OpenAIEngineConfig):
        """
        初始化 OpenAI 翻译引擎实例。
        Args:
            config: OpenAIEngineConfig 配置对象。
        """
        super().__init__(config)

        if not self.config.api_key:
            raise ValueError(
                "OpenAI API key is not configured. Please set TH_OPENAI_API_KEY in your environment or .env file."
            )

        if not self.config.base_url:
            raise ValueError(
                "OpenAI base_url is not configured. Please set TH_OPENAI_ENDPOINT in your environment or .env file."
            )

        self.client = openai.AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def _build_prompt(
        self, text: str, target_lang: str, source_lang: Optional[str]
    ) -> str:
        """构建发送给模型的完整 prompt。"""
        src_lang = source_lang if source_lang else self.config.default_source_lang

        return self.config.prompt_template.format(
            source_lang=src_lang, target_lang=target_lang, text=text
        )

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译方法。
        由于 OpenAI 客户端被配置为异步客户端，此方法不再直接支持同步调用。
        请使用 `atranslate_batch` 进行异步翻译。
        """
        raise NotImplementedError(
            "OpenAI engine is designed for async operations. Use atranslate_batch instead."
        )

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译。"""
        results: List[EngineBatchItemResult] = []
        for text in texts:
            prompt = self._build_prompt(text, target_lang, source_lang)
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": "You are a translation engine."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=1024,
                )

                translated_text_raw = response.choices[0].message.content
                if translated_text_raw is None:
                    logger.warning(
                        f"OpenAI API returned empty content for text: '{text}'"
                    )
                    results.append(
                        EngineError(
                            error_message="OpenAI API returned empty translated content.",
                            is_retryable=True,
                        )
                    )
                    continue

                translated_text = translated_text_raw.strip()

                if translated_text.startswith('"') and translated_text.endswith('"'):
                    translated_text = translated_text[1:-1]

                if not translated_text:
                    logger.warning(
                        f"OpenAI API returned empty string after stripping/quote removal for text: '{text}'"
                    )
                    results.append(
                        EngineError(
                            error_message="OpenAI API returned empty string after processing.",
                            is_retryable=True,
                        )
                    )
                    continue

                results.append(EngineSuccess(translated_text=translated_text))

            except openai.APIError as e:
                logger.error(f"OpenAI API Error for text '{text}': {e}", exc_info=True)
                is_retryable = False
                if hasattr(e, "status_code") and e.status_code in [
                    429,
                    500,
                    502,
                    503,
                    504,
                ]:
                    is_retryable = True

                results.append(
                    EngineError(
                        error_message=f"OpenAI API Error: {e}",
                        is_retryable=is_retryable,
                    )
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error during OpenAI translation for text '{text}': {e}",
                    exc_info=True,
                )
                results.append(
                    EngineError(
                        error_message=f"An unexpected error occurred: {e}",
                        is_retryable=True,
                    )
                )
        return results
