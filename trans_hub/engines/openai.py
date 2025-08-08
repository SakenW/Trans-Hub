# trans_hub/engines/openai.py
"""提供一个使用 OpenAI API 的翻译引擎。"""

import os
from typing import Any, cast

import httpx
import structlog
from pydantic import Field, HttpUrl, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.core.exceptions import ConfigurationError
from trans_hub.core.types import EngineBatchItemResult, EngineError, EngineSuccess
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)

_AsyncOpenAIClient: type | None = None
try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AsyncOpenAI,
        AuthenticationError,
        InternalServerError,
        PermissionDeniedError,
        RateLimitError,
    )
    from openai.types.chat import (
        ChatCompletionMessageParam,
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
    )

    _AsyncOpenAIClient = AsyncOpenAI
except ImportError:
    pass

logger = structlog.get_logger(__name__)


class OpenAIContext(BaseContextModel):
    """OpenAI 引擎的上下文模型。"""

    system_prompt: str | None = None
    prompt_template: str | None = None
    model: str | None = None
    temperature: float | None = None


class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):
    """OpenAI 引擎的配置模型。"""

    model_config = SettingsConfigDict(env_prefix="TH_OPENAI_", extra="ignore")
    api_key: SecretStr | None = Field(default=None, alias="th_openai_api_key")
    endpoint: HttpUrl = Field(default=cast(HttpUrl, "https://api.openai.com/v1"))
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.1
    default_prompt_template: str = (
        "Translate the following text from {source_lang} to {target_lang}. "
        "Return only the translated text, without any additional explanations "
        "or quotes.\n\n"
        'Text to translate: "{text}"'
    )
    timeout_total: float = 30.0
    timeout_connect: float = 5.0
    max_retries: int = 2

    @field_validator("endpoint", mode="before")
    @classmethod
    def _validate_endpoint(cls, v: Any, info: ValidationInfo) -> Any:
        if isinstance(v, str) and not v.strip():
            if info.field_name and info.field_name in cls.model_fields:
                return cls.model_fields[info.field_name].default
        return v


class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """使用 OpenAI API 的翻译引擎实现（生产级）。"""

    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext
    VERSION = "2.4.6"
    REQUIRES_SOURCE_LANG = True
    ACCEPTS_CONTEXT = True

    def __init__(self, config: OpenAIEngineConfig):
        super().__init__(config)
        if _AsyncOpenAIClient is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请安装 'openai' 库: "
                '"pip install "trans-hub[openai]"'
            )
        if not config.api_key:
            if "PYTEST_CURRENT_TEST" in os.environ or "CI" in os.environ:
                config.api_key = SecretStr("dummy-key-for-ci")
            else:
                raise ConfigurationError(
                    "OpenAI 引擎配置错误: 缺少 API 密钥 (TH_OPENAI_API_KEY)。"
                )

        assert config.api_key is not None
        timeout = httpx.Timeout(config.timeout_total, connect=config.timeout_connect)
        self.client: AsyncOpenAI = _AsyncOpenAIClient(
            api_key=config.api_key.get_secret_value(),
            base_url=str(config.endpoint),
            timeout=timeout,
            max_retries=config.max_retries,
        )

    async def initialize(self) -> None:
        assert self.config.api_key is not None
        if self.config.api_key.get_secret_value() == "dummy-key-for-ci":
            logger.warning("OpenAI 引擎处于CI/测试模式, 跳过健康检查。")
            await super().initialize()
            return
        logger.info(
            "OpenAI 引擎正在初始化并执行健康检查...", endpoint=str(self.config.endpoint)
        )
        try:
            await self.client.models.list(timeout=10)
            logger.info("✅ OpenAI 引擎健康检查通过。")
        except AuthenticationError as e:
            error_msg = (
                e.body.get("message", "无详细信息")
                if isinstance(e.body, dict)
                else str(e)
            )
            raise ConfigurationError(
                f"OpenAI API Key 无效或权限不足: {error_msg}"
            ) from e
        except APIConnectionError as e:
            raise ConfigurationError(
                f"无法连接到 OpenAI 端点 '{self.config.endpoint}': {e}"
            ) from e
        except Exception as e:
            raise ConfigurationError(f"OpenAI 引擎初始化失败: {e}") from e
        await super().initialize()

    async def close(self) -> None:
        if not self.client.is_closed():
            try:
                await self.client.close()
                logger.info("OpenAI 引擎的 HTTP 客户端已成功关闭。")
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    logger.warning(
                        "尝试关闭 OpenAI 客户端时事件循环已关闭, 可安全忽略。"
                    )
                else:
                    raise
        await super().close()

    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None,
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 执行单次 OpenAI 翻译调用，并对返回结构进行健壮性检查。"""
        final_source_lang = cast(str, source_lang)
        prompt_template = context_config.get(
            "prompt_template", self.config.default_prompt_template
        )
        model = context_config.get("model", self.config.model)
        temperature = context_config.get("temperature", self.config.temperature)
        system_prompt = context_config.get("system_prompt")

        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append(
                ChatCompletionSystemMessageParam(role="system", content=system_prompt)
            )

        prompt = prompt_template.format(
            text=text, source_lang=final_source_lang, target_lang=target_lang
        )
        messages.append(ChatCompletionUserMessageParam(role="user", content=prompt))

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=len(text.encode("utf-8")) * 3 + 150,
            )

            if not response.choices:
                return EngineError(
                    error_message="API 返回了空的 'choices' 列表。", is_retryable=True
                )

            message = response.choices[0].message
            content = message.content

            # [核心修复] 兼容 OpenAI 返回的多种 content 格式 (str 或 list of blocks)
            translated_text = ""
            if isinstance(content, str):
                translated_text = content
            elif isinstance(content, list):
                # 如果是列表，遍历所有部分并提取文本内容
                for part in content:
                    if hasattr(part, "text"):
                        translated_text += part.text

            if translated_text is None:  # 再次检查
                return EngineError(
                    error_message="API 返回的消息内容为 None。", is_retryable=True
                )

            translated_text = translated_text.strip().strip('"')
            if not translated_text:
                return EngineError(
                    error_message="API 返回了空内容。", is_retryable=True
                )

            return EngineSuccess(translated_text=translated_text)

        except (RateLimitError, InternalServerError, APIConnectionError) as e:
            return EngineError(error_message=str(e), is_retryable=True)
        except (PermissionDeniedError, AuthenticationError, APIStatusError) as e:
            error_msg = (
                e.body.get("message", str(e)) if isinstance(e.body, dict) else str(e)
            )
            return EngineError(
                error_message=f"API Error: {error_msg}", is_retryable=False
            )
        except Exception as e:
            return EngineError(error_message=f"未知引擎错误: {e}", is_retryable=True)
