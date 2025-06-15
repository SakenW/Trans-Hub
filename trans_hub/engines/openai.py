# trans_hub/engines/openai.py

"""
提供一个使用 OpenAI API (GPT 模型) 进行翻译的引擎。
此引擎是为纯异步操作而设计的，并通过 `IS_ASYNC_ONLY` 标志向 Coordinator 表明这一点。
"""

import asyncio
from types import ModuleType

# Ruff 修复：将模块级导入移至文件顶部
# Ruff 修复：将已弃用的 typing.Type 替换为 type
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

    # 使用 SecretStr 保护 API 密钥，避免其在日志中意外泄露
    api_key: SecretStr = Field(validation_alias="TH_OPENAI_API_KEY")
    # 使用 HttpUrl 验证 URL 格式
    endpoint: HttpUrl = Field(validation_alias="TH_OPENAI_ENDPOINT")
    model: str = Field(default="gpt-3.5-turbo", validation_alias="TH_OPENAI_MODEL")
    temperature: float = Field(default=0.1, validation_alias="TH_OPENAI_TEMPERATURE")

    # 默认的 prompt 模板，可以在上下文中被覆盖
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
    CONTEXT_MODEL = OpenAIContext  # 绑定上下文模型
    VERSION = "1.1.0"  # 版本号更新

    # 核心变更: 明确声明此引擎为纯异步
    IS_ASYNC_ONLY: bool = True
    # 核心变更: 明确要求提供源语言以保证翻译质量
    REQUIRES_SOURCE_LANG: bool = True

    def __init__(self, config: OpenAIEngineConfig):
        """初始化 OpenAI 翻译引擎实例。"""
        super().__init__(config)

        if _openai is None or _AsyncOpenAI is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请先安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        # Pydantic 已经处理了 api_key 和 endpoint 的存在性校验
        # 此处 _AsyncOpenAI 必然不为 None，cast 仅用于类型提示
        self.client = cast(type[_AsyncOpenAI], _AsyncOpenAI)(
            api_key=self.config.api_key.get_secret_value(),
            base_url=str(self.config.endpoint),  # 将 Pydantic URL 类型转换为字符串
        )

        logger.info(
            "openai_engine.initialized",  # 事件名称
            model=self.config.model,  # 结构化上下文
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
                    error_message="API 返回了空内容。", is_retryable=True
                )

            return EngineSuccess(translated_text=translated_text.strip())

        # Ruff 修复 (B030): 使用标准的 `except` 语句。
        # 在 __init__ 中已检查，此处 _openai 必然存在。
        except _openai.APIError as e:
            logger.error(
                "openai_api_error",
                text=text,
                error=str(e),
                exc_info=True,
                msg="OpenAI API 调用出错",
            )
            # 根据异常类型判断是否可重试
            openai_module = cast(ModuleType, _openai)
            is_retryable = isinstance(
                e,
                (
                    openai_module.RateLimitError,
                    openai_module.InternalServerError,
                    openai_module.APIConnectionError,
                ),
            )
            return EngineError(error_message=str(e), is_retryable=is_retryable)
        except Exception as e:
            logger.error(
                "openai_unexpected_error",
                text=text,
                error=str(e),
                exc_info=True,
                msg="发生未知错误",
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
        # 验证上下文类型
        if context is not None and not isinstance(context, OpenAIContext):
            return [
                EngineError(
                    error_message="OpenAI 引擎接收了无效的上下文类型",
                    is_retryable=False,
                )
            ] * len(texts)

        if not source_lang:
            # 此检查是双重保险，因为 REQUIRES_SOURCE_LANG=True 时，Coordinator 不应传入 None
            return [
                EngineError(
                    error_message="OpenAI 引擎需要提供源语言。",
                    is_retryable=False,
                )
            ] * len(texts)

        # 确定使用的 prompt 模板
        # 类型转换：已通过上下文验证，确保 context 是 OpenAIContext 实例
        openai_context = cast(OpenAIContext, context)
        prompt_template = (
            openai_context.prompt_template
            if openai_context and openai_context.prompt_template
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
