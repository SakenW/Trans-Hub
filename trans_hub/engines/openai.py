# trans_hub/engines/openai.py

"""
提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
此引擎是为纯异步操作而设计的，并通过 `IS_ASYNC_ONLY` 标志向 Coordinator 表明这一点。
"""

import asyncio
from types import ModuleType
from typing import TYPE_CHECKING, Optional, cast

import structlog
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

if TYPE_CHECKING:
    from openai import AsyncOpenAI

# 初始化模块变量
_openai: Optional[ModuleType] = None
_AsyncOpenAI: Optional[type["AsyncOpenAI"]] = None

# 懒加载：仅在 openai 库可用时才导入
try:
    import openai as _openai
    from openai import AsyncOpenAI as _AsyncOpenAI
except ImportError:
    pass

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
    api_key: SecretStr = Field(validation_alias="TH_OPENAI_API_KEY")
    endpoint: HttpUrl = Field(validation_alias="TH_OPENAI_ENDPOINT")
    model: str = Field(default="gpt-3.5-turbo", validation_alias="TH_OPENAI_MODEL")
    temperature: float = Field(default=0.1, validation_alias="TH_OPENAI_TEMPERATURE")
    default_prompt_template: str = (
        "你是一个专业的翻译引擎。"
        "请将以下文本从 {source_lang} 翻译成 {target_lang}。"
        "请只返回翻译后的文本，不要包含任何额外的解释或多余的引号。"
        '\n\n待翻译文本："{text}"'
    )


# 3. 实现引擎主类
class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """一个使用 OpenAI (GPT) 进行翻译的纯异步引擎。"""

    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext
    VERSION = "1.1.0"
    IS_ASYNC_ONLY: bool = True
    REQUIRES_SOURCE_LANG: bool = True

    def __init__(self, config: OpenAIEngineConfig):
        """初始化 OpenAI 翻译引擎实例。"""
        super().__init__(config)

        if _openai is None or _AsyncOpenAI is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请先安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        # MYPY 修复 (misc, valid-type):
        # __init__ 中的检查已经保证 _AsyncOpenAI 不是 None。
        # mypy 可以通过这个逻辑，因此不再需要复杂的 cast。
        self.client = _AsyncOpenAI(
            api_key=self.config.api_key.get_secret_value(),
            base_url=str(self.config.endpoint),
        )

        logger.info(
            "openai_engine.initialized",
            model=self.config.model,
            endpoint=str(self.config.endpoint),
            msg="OpenAI 引擎初始化成功",
        )

    def translate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
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
        # MYPY 修复 (union-attr):
        # 添加 assert 明确告诉 mypy，如果代码能执行到这里，_openai 模块必然已被加载。
        # 这消除了 mypy 对 `_openai.APIError` 访问的疑虑。
        assert _openai, "OpenAI 模块应在初始化时加载"

        prompt = prompt_template.format(
            text=text, source_lang=source_lang, target_lang=target_lang
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=len(text.encode("utf-8")) * 2 + 100,
            )

            translated_text = response.choices[0].message.content or ""
            if not translated_text:
                logger.warning(
                    "OpenAI API 返回了空内容",
                    text=text,
                )
                return EngineError(
                    error_message="API 返回了空内容。", is_retryable=True
                )

            return EngineSuccess(translated_text=translated_text.strip())

        except _openai.APIError as e:
            logger.error("openai_api_error", text=text, error=str(e), exc_info=True, msg="OpenAI API 调用出错")
            is_retryable = isinstance(
                e,
                (
                    _openai.RateLimitError,
                    _openai.InternalServerError,
                    _openai.APIConnectionError,
                ),
            )
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            logger.error(
                "openai_unexpected_error", text=text, error=str(e), exc_info=True, msg="发生未知错误"
            )
            return EngineError(error_message=str(e), is_retryable=True)

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """异步批量翻译，通过 asyncio.gather 并发执行。"""
        if context is not None and not isinstance(context, OpenAIContext):
            return [
                EngineError(
                    error_message="OpenAI 引擎接收了无效的上下文类型",
                    is_retryable=False,
                )
            ] * len(texts)

        if not source_lang:
            return [
                EngineError(
                    error_message="OpenAI 引擎需要提供源语言。",
                    is_retryable=False,
                )
            ] * len(texts)

        openai_context = cast(OpenAIContext, context)
        prompt_template = (
            openai_context.prompt_template
            if openai_context and openai_context.prompt_template
            else self.config.default_prompt_template
        )

        tasks = [
            self._translate_single_text(text, target_lang, source_lang, prompt_template)
            for text in texts
        ]

        results = await asyncio.gather(*tasks)
        return results
