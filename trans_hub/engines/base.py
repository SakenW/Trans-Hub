# trans_hub/engines/base.py
"""
本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。
v3.1.0 修复: 彻底解耦引擎与主配置。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, Union

from pydantic import BaseModel, Field

from trans_hub.core.types import EngineBatchItemResult, EngineError, EngineSuccess
from trans_hub.rate_limiter import RateLimiter

_ConfigType = TypeVar("_ConfigType", bound="BaseEngineConfig")


class BaseContextModel(BaseModel):
    """引擎特定上下文的基础模型。"""

    pass


class BaseEngineConfig(BaseModel):
    """所有引擎配置模型的基类，提供了通用的速率与并发控制选项。"""

    rpm: int | None = Field(
        default=None, description="每分钟最大请求数 (Requests Per Minute)", gt=0
    )
    rps: int | None = Field(
        default=None, description="每秒最大请求数 (Requests Per Second)", gt=0
    )
    max_concurrency: int | None = Field(
        default=None, description="最大并发请求数", gt=0
    )
    max_batch_size: int = Field(default=50, gt=0)


class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类，内置速率限制和并发控制。"""

    CONFIG_MODEL: type[_ConfigType]
    CONTEXT_MODEL: type[BaseContextModel] = BaseContextModel
    VERSION: str = "1.0.0"
    REQUIRES_SOURCE_LANG: bool = False
    ACCEPTS_CONTEXT: bool = False

    def __init__(self, config: _ConfigType):
        self.config = config
        self._rate_limiter: RateLimiter | None = None
        self._concurrency_semaphore: asyncio.Semaphore | None = None
        self.initialized: bool = False

        if config.rpm:
            self._rate_limiter = RateLimiter(
                refill_rate=config.rpm / 60, capacity=config.rpm
            )
        elif config.rps:
            self._rate_limiter = RateLimiter(
                refill_rate=config.rps, capacity=config.rps
            )

        if config.max_concurrency:
            self._concurrency_semaphore = asyncio.Semaphore(config.max_concurrency)

    @property
    def name(self) -> str:
        """从类名自动推断引擎的名称。"""
        return self.__class__.__name__.replace("Engine", "").lower()

    async def initialize(self) -> None:
        """引擎的异步初始化钩子，用于设置连接池等。"""
        self.initialized = True

    async def close(self) -> None:
        """引擎的异步关闭钩子，用于安全释放资源。"""
        self.initialized = False

    @abstractmethod
    async def _execute_single_translation(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None,
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[子类实现] 真正执行单次翻译的逻辑。"""
        ...

    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: str | None,
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[模板方法] 执行单次翻译，应用并发和速率限制。"""
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        if self._concurrency_semaphore:
            async with self._concurrency_semaphore:
                return await self._execute_single_translation(
                    text, target_lang, source_lang, context_config
                )
        else:
            return await self._execute_single_translation(
                text, target_lang, source_lang, context_config
            )

    def _get_context_config(self, context: BaseContextModel | None) -> dict[str, Any]:
        if context and isinstance(context, self.CONTEXT_MODEL):
            return context.model_dump(exclude_unset=True)
        return {}

    def validate_and_parse_context(
        self, context_dict: dict[str, Any] | None
    ) -> Union[BaseContextModel, EngineError]:
        if not self.ACCEPTS_CONTEXT or not context_dict:
            return BaseContextModel()
        try:
            return self.CONTEXT_MODEL.model_validate(context_dict)
        except Exception as e:
            error_msg = f"上下文验证失败: {e}"
            return EngineError(error_message=error_msg, is_retryable=False)

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: str | None = None,
        context: BaseContextModel | None = None,
    ) -> list[EngineBatchItemResult]:
        if self.REQUIRES_SOURCE_LANG and not source_lang:
            error_msg = f"引擎 '{self.__class__.__name__}' 需要提供源语言。"
            return [EngineError(error_message=error_msg, is_retryable=False)] * len(
                texts
            )
        context_config = self._get_context_config(context)
        tasks = [
            self._atranslate_one(text, target_lang, source_lang, context_config)
            for text in texts
        ]
        results: list[
            Union[EngineBatchItemResult, BaseException]
        ] = await asyncio.gather(*tasks, return_exceptions=True)

        final_results: list[EngineBatchItemResult] = []
        for res in results:
            if isinstance(res, EngineSuccess | EngineError):
                final_results.append(res)
            elif isinstance(res, BaseException):
                error_res = EngineError(
                    error_message=f"引擎执行异常: {res.__class__.__name__}: {res}",
                    is_retryable=True,
                )
                final_results.append(error_res)
            else:
                unhandled_error = EngineError(
                    error_message=f"未知的 gather 结果类型: {type(res)}",
                    is_retryable=False,
                )
                final_results.append(unhandled_error)
        return final_results
