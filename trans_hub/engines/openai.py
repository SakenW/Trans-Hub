# trans_hub/engines/openai.py

"""
提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
此引擎是为纯异步操作而设计的，并通过 `IS_ASYNC_ONLY` 标志向 Coordinator 表明这一点。
"""
import asyncio
from typing import List, Optional

import structlog

# 懒加载：仅在 openai 库可用时才导入
try:
    import openai
    from openai import AsyncOpenAI
except ImportError:
    openai = None
    AsyncOpenAI = None

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

logger = structlog.get_logger(__name__)


# 1. 定义引擎特定的上下文模型
class OpenAIContext(BaseContextModel):
    """OpenAI 引擎的上下文模型。
    允许在每次请求时覆盖默认的 prompt 模板。
    """

    prompt_template: Optional[str] = None


# 2. 定义配置模型，使用更严格的 Pydantic 类型
class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):
    """OpenAI 引擎的特定配置。"""

    model_config = SettingsConfigDict(extra="ignore")

    # 使用 SecretStr 保护 API 密钥，避免其在日志中意外泄露
    api_key: SecretStr = Field(validation_alias="TH_OPENAI_API_KEY")
    # 使用 HttpUrl 验证 URL 格式
    endpoint: HttpUrl = Field(validation_alias="TH_OPENAI_ENDPOINT")
    model: str = Field(default="gpt-3.5-turbo", validation_alias="TH_OPENAI_MODEL")
    temperature: float = Field(default=0.1, validation_alias="TH_OPENAI_TEMPERATURE")

    # 默认的 prompt 模板，可以在上下文中被覆盖
    default_prompt_template: str = (
        "You are a professional translation engine. "
        "Translate the following text from {source_lang} to {target_lang}. "
        "Return only the translated text, without any additional explanations or surrounding quotes."
        '\n\nText to translate: "{text}"'
    )


# 3. 实现引擎主类
class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """一个使用 OpenAI (GPT) 进行翻译的纯异步引擎。"""

    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext  # 绑定上下文模型
    VERSION = "1.1.0"  # 版本号更新

    # 核心变更: 明确声明此引擎为纯异步
    IS_ASYNC_ONLY: bool = True
    # 核心变更: 明确要求提供源语言以保证翻译质量
    REQUIRES_SOURCE_LANG: bool = True

    def __init__(self, config: OpenAIEngineConfig):
        """初始化 OpenAI 翻译引擎实例。"""
        super().__init__(config)

        if openai is None or AsyncOpenAI is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请先安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        # Pydantic 已经处理了 api_key 和 endpoint 的存在性校验
        self.client = AsyncOpenAI(
            api_key=self.config.api_key.get_secret_value(),
            base_url=str(self.config.endpoint),  # 将 Pydantic URL 类型转换为字符串
        )

        # 核心修复: 修正 logger.info 的调用方式，符合 structlog 的用法
        logger.info(
            "openai_engine.initialized",  # 事件名称
            model=self.config.model,  # 结构化上下文
            endpoint=str(self.config.endpoint),
        )

    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[OpenAIContext] = None,
    ) -> List[EngineBatchItemResult]:
        """同步批量翻译方法。此方法不应被调用。"""
        raise NotImplementedError(
            "OpenAI 引擎是为纯异步操作设计的。Coordinator 应该调用 atranslate_batch。"
        )

    async def _translate_single_text(
        self,
        text: str,
        target_lang: str,
        source_lang: str,
        prompt_template: str,
    ) -> EngineBatchItemResult:
        """异步翻译单个文本，并处理其特定错误。"""
        prompt = prompt_template.format(
            text=text, source_lang=source_lang, target_lang=target_lang
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=len(text.encode("utf-8")) * 2 + 100,  # 粗略估计所需 token
            )

            translated_text = response.choices[0].message.content or ""
            if not translated_text:
                logger.warning(
                    "OpenAI API 返回了空内容",
                    text=text,
                )
                return EngineError(
                    error_message="API returned empty content.", is_retryable=True
                )

            return EngineSuccess(translated_text=translated_text.strip())

        except openai.APIError as e:
            logger.error("openai_api_error", text=text, error=str(e), exc_info=True)
            # 根据异常类型判断是否可重试
            is_retryable = isinstance(
                e,
                (
                    openai.RateLimitError,
                    openai.InternalServerError,
                    openai.APIConnectionError,
                ),
            )
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            logger.error(
                "openai_unexpected_error", text=text, error=str(e), exc_info=True
            )
            return EngineError(error_message=str(e), is_retryable=True)

    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[OpenAIContext] = None,
    ) -> List[EngineBatchItemResult]:
        """异步批量翻译，通过 asyncio.gather 并发执行。"""
        if not source_lang:
            # 此检查是双重保险，因为 REQUIRES_SOURCE_LANG=True 时，Coordinator 不应传入 None
            return [
                EngineError(
                    error_message="OpenAI engine requires a source language.",
                    is_retryable=False,
                )
            ] * len(texts)

        # 确定使用的 prompt 模板
        prompt_template = (
            context.prompt_template
            if context and context.prompt_template
            else self.config.default_prompt_template
        )

        # 创建所有并发任务
        tasks = [
            self._translate_single_text(text, target_lang, source_lang, prompt_template)
            for text in texts
        ]

        # 并发执行并收集结果
        results = await asyncio.gather(*tasks)
        return results
