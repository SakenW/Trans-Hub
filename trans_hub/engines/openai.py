"""trans_hub/engines/openai.py (v1.0 Final)

提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
实现了从 .env 主动加载配置的最佳实践，并支持异步翻译。
"""

import logging  # 导入 logging 模块
from typing import List, Optional

import openai  # 导入 openai 库的顶层模块

# 使用 pydantic Field 来创建别名，实现内外名称解耦
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 导入基类和相关模型，并引入泛型支持
from trans_hub.engines.base import BaseContextModel, BaseTranslationEngine

# 导入 _ConfigType
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 初始化日志记录器
logger = logging.getLogger(__name__)


class OpenAIEngineConfig(BaseSettings):
    """OpenAI 引擎的特定配置。
    通过 pydantic-settings 从环境变量中加载配置。
    """

    # model_config 指示 pydantic-settings 如何加载配置
    model_config = SettingsConfigDict(
        # 不再需要 env_prefix，因为 validation_alias 提供了完整的变量名
        # 不再需要 env_file，因为我们将通过 dotenv 主动加载
        extra="ignore"
    )

    # 保持内部字段名清晰、符合 Python 风格
    # 通过 validation_alias 映射到具体的环境变量名
    api_key: Optional[str] = Field(default=None, validation_alias="TH_OPENAI_API_KEY")
    base_url: Optional[str] = Field(default=None, validation_alias="TH_OPENAI_ENDPOINT")
    model: str = Field(default="gpt-3.5-turbo", validation_alias="TH_OPENAI_MODEL")

    # 这两个字段没有对应的环境变量，所以会使用代码中定义的默认值
    prompt_template: str = (
        "You are a professional translation engine. "
        "Translate the following text from {source_lang} to {target_lang}. "
        "Do not output any other text, explanation, or notes. "
        "Just return the translated text.\n\n"
        'Text to translate: "{text}"'
    )
    default_source_lang: str = "auto"


# 核心修复：将 OpenAIEngine 声明为 BaseTranslationEngine 的泛型子类
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
        # Mypy 现在能够正确识别 self.config 的类型为 OpenAIEngineConfig
        super().__init__(config)

        if not self.config.api_key:  # 检查 API Key 是否存在
            raise ValueError(
                "OpenAI API key is not configured. Please set TH_OPENAI_API_KEY in your environment or .env file."
            )

        # 强制 base_url 存在，如果它不是 None
        # 如果 base_url 可以是 None，但 client 初始化时必须有，则需要更复杂逻辑或默认值
        # 目前看来，您的 prompt_template 明确要求 base_url
        if not self.config.base_url:
            raise ValueError(
                "OpenAI base_url is not configured. Please set TH_OPENAI_ENDPOINT in your environment or .env file."
            )

        # 核心修复：使用 AsyncOpenAI 来实现真正的异步行为
        self.client = openai.AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def _build_prompt(
        self, text: str, target_lang: str, source_lang: Optional[str]
    ) -> str:
        """构建发送给模型的完整 prompt。"""
        # 如果 source_lang 为 None，使用 default_source_lang
        src_lang = source_lang if source_lang else self.config.default_source_lang

        # Mypy 现在知道 self.config.prompt_template 是 str
        # 且 src_lang 总是 str，因为 default_source_lang 是 str
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
                # 使用异步客户端进行 await 调用
                response = await self.client.chat.completions.create(
                    model=self.config.model,  # Mypy 现在知道 self.config.model 是 str
                    messages=[
                        {"role": "system", "content": "You are a translation engine."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=1024,
                )

                # 修复：检查 content 是否为 None 后再 strip
                translated_text_raw = response.choices[0].message.content
                if translated_text_raw is None:
                    logger.warning(
                        f"OpenAI API returned empty content for text: '{text}'"
                    )
                    results.append(
                        EngineError(
                            error_message="OpenAI API returned empty translated content.",
                            is_retryable=True,  # 假设空内容可能是暂时性问题
                        )
                    )
                    continue  # 跳过当前文本，处理下一个

                translated_text = translated_text_raw.strip()

                # 处理 GPT 模型可能返回的带引号的翻译结果
                if translated_text.startswith('"') and translated_text.endswith('"'):
                    translated_text = translated_text[1:-1]

                # 确保翻译结果不为空字符串，否则也视作错误
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
                # 修复：安全访问 status_code，尽管通常 APIError 会有此属性
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
