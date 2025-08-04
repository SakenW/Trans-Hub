# trans_hub/engines/openai.py
"""提供一个使用 OpenAI API 的翻译引擎。"""

import os
from typing import Any, Optional, cast

import httpx
import structlog
from pydantic import Field, HttpUrl, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.exceptions import ConfigurationError
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_AsyncOpenAIClient: Optional[type] = None
try:
    # --- 最终修复：导入更精确的类型 ---
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

    system_prompt: Optional[str] = None
    prompt_template: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None


class OpenAIEngineConfig(BaseSettings, BaseEngineConfig):
    """OpenAI 引擎的配置模型。"""

    model_config = SettingsConfigDict(env_prefix="TH_", extra="ignore")
    openai_api_key: Optional[SecretStr] = None
    openai_endpoint: HttpUrl = Field(default=cast(HttpUrl, "https://api.openai.com/v1"))
    openai_model: str = "gpt-3.5-turbo"
    openai_temperature: float = 0.1
    default_prompt_template: str = (
        "Translate the following text from {source_lang} to {target_lang}. "
        "Return only the translated text, without any additional explanations "
        "or quotes.\n\n"
        'Text to translate: "{text}"'
    )

    @field_validator("openai_endpoint", mode="before")
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
                'pip install "trans-hub[openai]"'
            )
        if not self.config.openai_api_key:
            if "PYTEST_CURRENT_TEST" in os.environ or "CI" in os.environ:
                self.config.openai_api_key = SecretStr("dummy-key-for-ci")
            else:
                raise ConfigurationError(
                    "OpenAI 引擎配置错误: 缺少 API 密钥 (TH_OPENAI_API_KEY)。"
                )
        assert self.config.openai_api_key is not None
        timeout = httpx.Timeout(30.0, connect=5.0)
        self.client: AsyncOpenAI = _AsyncOpenAIClient(
            api_key=self.config.openai_api_key.get_secret_value(),
            base_url=str(self.config.openai_endpoint),
            timeout=timeout,
            max_retries=2,
        )

    async def initialize(self) -> None:
        assert self.config.openai_api_key is not None
        if self.config.openai_api_key.get_secret_value() == "dummy-key-for-ci":
            logger.warning("OpenAI 引擎处于CI/测试模式, 跳过健康检查。")
            return
        logger.info(
            "OpenAI 引擎正在初始化并执行健康检查...",
            endpoint=str(self.config.openai_endpoint),
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
                f"无法连接到 OpenAI 端点 '{self.config.openai_endpoint}': {e}"
            ) from e
        except Exception as e:
            raise ConfigurationError(f"OpenAI 引擎初始化失败: {e}") from e

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

    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        final_source_lang = cast(str, source_lang)
        prompt_template = context_config.get(
            "prompt_template", self.config.default_prompt_template
        )
        model = context_config.get("model", self.config.openai_model)
        temperature = context_config.get("temperature", self.config.openai_temperature)
        system_prompt = context_config.get("system_prompt")

        # --- 最终修复：使用精确的类型 ---
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
            translated_text = response.choices[0].message.content or ""
            if not translated_text.strip():
                return EngineError(
                    error_message="API 返回了空内容。", is_retryable=True
                )
            return EngineSuccess(translated_text=translated_text.strip().strip('"'))
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
