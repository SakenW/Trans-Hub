# trans_hub/engines/base.py
"""
本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。

它规定了引擎的配置模型、上下文模型以及核心的异步翻译方法接口。
此版本通过引入 `_atranslate_one` 抽象方法，将批处理和上下文解析的
通用逻辑提取到基类中，极大地简化了具体引擎的实现。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar, Union, cast

from pydantic import BaseModel

from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

_ConfigType = TypeVar("_ConfigType", bound="BaseEngineConfig")


class BaseContextModel(BaseModel):
    """所有引擎特定上下文模型的基类。"""

    pass


class BaseEngineConfig(BaseModel):
    """所有引擎配置模型的基类。"""

    rpm: Optional[int] = None
    rps: Optional[int] = None
    max_concurrency: Optional[int] = None
    max_batch_size: int = 50


class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类。所有引擎实现都必须继承此类。"""

    CONFIG_MODEL: type[_ConfigType]
    CONTEXT_MODEL: type[BaseContextModel] = BaseContextModel
    VERSION: str = "1.0.0"
    REQUIRES_SOURCE_LANG: bool = False
    ACCEPTS_CONTEXT: bool = False

    def __init__(self, config: _ConfigType):
        self.config = config

    # --- 核心修正 1.2.1: 添加生命周期钩子 ---
    async def initialize(self) -> None:
        """
        [可选实现] 初始化引擎所需的异步资源（如网络连接池）。
        此方法将在 Coordinator 初始化时被调用。
        """
        pass

    async def close(self) -> None:
        """
        [可选实现] 安全关闭引擎占用的异步资源。
        此方法将在 Coordinator 关闭时被调用。
        """
        pass

    @abstractmethod
    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """[必须实现] 翻译单个文本的核心抽象方法。"""
        ...

    def _get_context_config(
        self, context: Optional[BaseContextModel]
    ) -> dict[str, Any]:
        """[内部工具] 从上下文模型中提取配置字典。"""
        if context and isinstance(context, self.CONTEXT_MODEL):
            return cast(dict[str, Any], context.model_dump(exclude_unset=True))
        return {}

    def validate_and_parse_context(
        self, context_dict: Optional[dict[str, Any]]
    ) -> Union[BaseContextModel, EngineError]:
        """[便利工具] 验证并解析一个原始的 context 字典。"""
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
        """[通用逻辑] 并发地翻译一批文本。"""
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
