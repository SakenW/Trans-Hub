"""
trans_hub/engines/openai.py (v1.0 Final)

提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
实现了从 .env 主动加载配置的最佳实践。
"""
import os
from typing import List, Optional

# 使用 pydantic Field 来创建别名，实现内外名称解耦
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

import openai
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess


class OpenAIEngineConfig(BaseSettings):
    """
    OpenAI 引擎的特定配置。
    通过 pydantic-settings 从环境变量中加载配置。
    """
    # model_config 指示 pydantic-settings 如何加载配置
    model_config = SettingsConfigDict(
        # 不再需要 env_prefix，因为 validation_alias 提供了完整的变量名
        # 不再需要 env_file，因为我们将通过 dotenv 主动加载
        extra='ignore'
    )
    
    # 保持内部字段名清晰、符合 Python 风格
    # 通过 validation_alias 映射到具体的环境变量名
    api_key: Optional[str] = Field(default=None, validation_alias='TH_OPENAI_API_KEY')
    base_url: Optional[str] = Field(default=None, validation_alias='TH_OPENAI_ENDPOINT')
    model: str = Field(default="gpt-3.5-turbo", validation_alias='TH_OPENAI_MODEL')
    
    # 这两个字段没有对应的环境变量，所以会使用代码中定义的默认值
    prompt_template: str = (
        "You are a professional translation engine. "
        "Translate the following text from {source_lang} to {target_lang}. "
        "Do not output any other text, explanation, or notes. "
        "Just return the translated text.\n\n"
        "Text to translate: \"{text}\""
    )
    default_source_lang: str = "auto"


class OpenAIEngine(BaseTranslationEngine):
    """一个使用 OpenAI (GPT) 进行翻译的引擎。"""
    CONFIG_MODEL = OpenAIEngineConfig
    VERSION = "1.0.0"
    REQUIRES_SOURCE_LANG = False 

    def __init__(self, config: OpenAIEngineConfig):
        super().__init__(config)

        if not self.config.base_url:
            raise ValueError("OpenAI base_url is not configured. Please set TH_OPENAI_ENDPOINT in your environment or .env file.")

        self.client = openai.OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )
        
    def _build_prompt(self, text: str, target_lang: str, source_lang: Optional[str]) -> str:
        """构建发送给模型的完整 prompt。"""
        src_lang = source_lang if source_lang else self.config.default_source_lang
        return self.config.prompt_template.format(
            source_lang=src_lang, target_lang=target_lang, text=text
        )

    def translate_batch(
        self, texts: List[str], target_lang: str,
        source_lang: Optional[str] = None, context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译。"""
        results: List[EngineBatchItemResult] = []
        for text in texts:
            prompt = self._build_prompt(text, target_lang, source_lang)
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": "You are a translation engine."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0, max_tokens=1024,
                )
                
                translated_text = response.choices[0].message.content.strip()
                if translated_text.startswith('"') and translated_text.endswith('"'):
                    translated_text = translated_text[1:-1]
                results.append(EngineSuccess(translated_text=translated_text))

            except openai.APIError as e:
                is_retryable = e.status_code in [429, 500, 502, 503, 504]
                results.append(EngineError(
                    error_message=f"OpenAI API Error: {e}", is_retryable=is_retryable
                ))
            except Exception as e:
                results.append(EngineError(
                    error_message=f"An unexpected error occurred: {e}", is_retryable=True
                ))
        return results

    async def atranslate_batch(
        self, texts: List[str], target_lang: str,
        source_lang: Optional[str] = None, context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译 (待实现)。"""
        return self.translate_batch(texts, target_lang, source_lang, context)