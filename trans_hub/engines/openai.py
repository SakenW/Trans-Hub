# trans_hub/engines/openai.py
"""
提供一个使用 OpenAI API 的翻译引擎。
本版本经过生产级加固，包含了启动时健康检查和更精细的错误处理，
并能健壮地处理CI环境中的空环境变量。
"""

import os
from typing import Any, Optional, cast

import httpx
import structlog
from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub.engines.meta import register_engine_config
from trans_hub.exceptions import ConfigurationError
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_AsyncOpenAIClient: Optional[type] = None
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
        "Return only the translated text, without any additional explanations or quotes.\n\n"
        'Text to translate: "{text}"'
    )

    @field_validator("openai_endpoint", mode="before")
    @classmethod
    def _validate_endpoint(cls, v: Any) -> Optional[Any]:
        """如果环境变量为空字符串，则返回 None，以便 Pydantic 使用默认值。"""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class OpenAIEngine(BaseTranslationEngine[OpenAIEngineConfig]):
    """使用 OpenAI API 的翻译引擎实现（生产级）。"""

    CONFIG_MODEL = OpenAIEngineConfig
    CONTEXT_MODEL = OpenAIContext
    VERSION = "2.4.0"
    REQUIRES_SOURCE_LANG = True
    ACCEPTS_CONTEXT = True

    def __init__(self, config: OpenAIEngineConfig):
        super().__init__(config)
        if _AsyncOpenAIClient is None:
            raise ImportError(
                "要使用 OpenAIEngine, 请安装 'openai' 库: pip install \"trans-hub[openai]\""
            )

        if not self.config.openai_api_key:
            if "PYTEST_CURRENT_TEST" in os.environ or "CI" in os.environ:
                self.config.openai_api_key = SecretStr("dummy-key-for-ci")
            else:
                raise ConfigurationError(
                    "OpenAI 引擎配置错误: 缺少 API 密钥 (TH_OPENAI_API_KEY)。"
                )

        assert self.config.openai_api_key is not None

        # --- 核心修正：遵循 openai v1.x+ 的最佳实践 ---
        # 直接将 api_key 和 base_url 传递给客户端，而不是预构建 http_client。
        # httpx.Timeout 用于更精细的超时控制。
        timeout = httpx.Timeout(30.0, connect=5.0)
        self.client: AsyncOpenAI = _AsyncOpenAIClient(
            api_key=self.config.openai_api_key.get_secret_value(),
            base_url=str(self.config.openai_endpoint),
            timeout=timeout,
            max_retries=2,
        )

    async def initialize(self) -> None:
        """[实现] 初始化引擎并执行健康检查，验证网络和认证。"""
        assert self.config.openai_api_key is not None
        if self.config.openai_api_key.get_secret_value() == "dummy-key-for-ci":
            logger.warning("OpenAI 引擎处于CI/测试模式，跳过健康检查。")
            return

        logger.info(
            "OpenAI 引擎正在初始化并执行健康检查...",
            endpoint=str(self.config.openai_endpoint),
        )
        try:
            await self.client.models.list(timeout=10)
            logger.info("✅ OpenAI 引擎健康检查通过：成功连接到 API 端点并完成认证。")
        except AuthenticationError as e:
            logger.error(
                "OpenAI API 认证失败！请检查您的 API Key 是否正确或已过期。",
                exc_info=False,
            )
            error_msg = (
                e.body.get("message", "无详细信息")
                if isinstance(e.body, dict)
                else str(e)
            )
            raise ConfigurationError(
                f"OpenAI API Key 无效或权限不足: {error_msg}"
            ) from e
        except APIConnectionError as e:
            logger.error(
                "无法连接到 OpenAI API 端点！请检查网络或 TH_OPENAI_ENDPOINT 配置。",
                exc_info=False,
            )
            raise ConfigurationError(
                f"无法连接到 OpenAI 端点 '{self.config.openai_endpoint}': {e}"
            ) from e
        except Exception as e:
            logger.error("OpenAI 引擎初始化期间发生未知错误。", exc_info=True)
            raise ConfigurationError(f"OpenAI 引擎初始化失败: {e}") from e

    async def close(self) -> None:
        """[实现] 安全地关闭引擎占用的 HTTP 客户端资源。"""
        if hasattr(self.client, "close"):
            await self.client.close()
        logger.info("OpenAI 引擎的 HTTP 客户端已关闭。")

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[实现] 异步翻译单个文本，包含精细的错误处理。"""
        final_source_lang = cast(str, source_lang)
        prompt_template = context_config.get(
            "prompt_template", self.config.default_prompt_template
        )
        model = context_config.get("model", self.config.openai_model)
        temperature = context_config.get("temperature", self.config.openai_temperature)
        system_prompt = context_config.get("system_prompt")
        messages: list[dict[str, Any]] = []
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
            if not translated_text.strip():
                return EngineError(
                    error_message="API 返回了空内容。", is_retryable=True
                )
            return EngineSuccess(translated_text=translated_text.strip().strip('"'))
        except (RateLimitError, InternalServerError, APIConnectionError) as e:
            logger.warning(
                "OpenAI API 调用遇到可重试错误",
                error_type=type(e).__name__,
                error=str(e),
            )
            return EngineError(error_message=str(e), is_retryable=True)
        except (PermissionDeniedError, AuthenticationError) as e:
            logger.error(
                "OpenAI API 调用遇到不可重试的权限/认证错误",
                error_type=type(e).__name__,
                error=str(e),
            )
            error_msg = (
                e.body.get("message", str(e)) if isinstance(e.body, dict) else str(e)
            )
            return EngineError(error_message=error_msg, is_retryable=False)
        except APIStatusError as e:
            logger.error("OpenAI API 调用出错", status_code=e.status_code, error=str(e))
            error_msg = (
                e.body.get("message", str(e)) if isinstance(e.body, dict) else str(e)
            )
            return EngineError(
                error_message=f"API Error (HTTP {e.status_code}): {error_msg}",
                is_retryable=False,
            )
        except Exception as e:
            logger.error(
                "OpenAI 引擎发生未知错误", error_type=type(e).__name__, exc_info=True
            )
            return EngineError(error_message=f"未知引擎错误: {e}", is_retryable=True)


register_engine_config("openai", OpenAIEngineConfig)
