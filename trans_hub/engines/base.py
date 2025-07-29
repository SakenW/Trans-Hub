# trans_hub/engines/base.py
"""本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar, Union

from pydantic import BaseModel

from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_ConfigType = TypeVar("_ConfigType", bound="BaseEngineConfig")


class BaseContextModel(BaseModel):
    pass


class BaseEngineConfig(BaseModel):
    rpm: Optional[int] = None
    rps: Optional[int] = None
    max_concurrency: Optional[int] = None
    max_batch_size: int = 50


class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类。"""

    CONFIG_MODEL: type[_ConfigType]
    CONTEXT_MODEL: type[BaseContextModel] = BaseContextModel
    VERSION: str = "1.0.0"
    REQUIRES_SOURCE_LANG: bool = False
    ACCEPTS_CONTEXT: bool = False

    def __init__(self, config: _ConfigType):
        self.config = config

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    @abstractmethod
    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult: ...

    def _get_context_config(
        self, context: Optional[BaseContextModel]
    ) -> dict[str, Any]:
        if context and isinstance(context, self.CONTEXT_MODEL):
            return context.model_dump(exclude_unset=True)
        return {}

    def validate_and_parse_context(
        self, context_dict: Optional[dict[str, Any]]
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
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
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
            if isinstance(res, (EngineSuccess, EngineError)):
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
