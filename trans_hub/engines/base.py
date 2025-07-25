# trans_hub/engines/base.py (重构后 v2.0)
"""本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。

它规定了引擎的配置模型、上下文模型以及核心的异步翻译方法接口。
此版本通过引入 `_atranslate_one` 抽象方法，将批处理和上下文解析的
通用逻辑提取到基类中，极大地简化了具体引擎的实现。
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

from trans_hub.types import EngineBatchItemResult

# ==============================================================================
#  基础模型定义 (无变动)
# ==============================================================================

class BaseContextModel(BaseModel):
    """所有引擎特定上下文模型的基类。."""
    pass

class BaseEngineConfig(BaseModel):
    """所有引擎配置模型的基类。."""
    rpm: Optional[int] = None
    rps: Optional[int] = None
    max_concurrency: Optional[int] = None

_ConfigType = TypeVar("_ConfigType", bound=BaseEngineConfig)

# ==============================================================================
#  抽象引擎基类 (核心重构)
# ==============================================================================

class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类。所有引擎实现都必须继承此类。

    核心职责（由基类完成）：
    - 编排批量请求的并发执行。
    - 统一处理翻译上下文（context）。
    - 提供一个统一的、健壮的 `atranslate_batch` 接口。

    子类职责：
    - 实现 `_atranslate_one` 方法，只关注单个文本的翻译逻辑。
    """

    CONFIG_MODEL: type[_ConfigType]
    CONTEXT_MODEL: type[BaseContextModel] = BaseContextModel
    VERSION: str = "1.0.0"
    REQUIRES_SOURCE_LANG: bool = False

    def __init__(self, config: _ConfigType):
        self.config = config

    @abstractmethod
    async def _atranslate_one(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str],
        # 新增参数：将解析后的上下文配置传入
        context_config: dict[str, Any],
    ) -> EngineBatchItemResult:
        """
        [异步] 翻译单个文本。这是所有引擎子类必须实现的核心方法。

        此方法只应关心如何使用给定的参数翻译一个文本，而无需关心
        批处理、并发、上下文解析等外围逻辑。

        参数:
            text: 需要翻译的单个字符串。
            target_lang: 目标语言代码。
            source_lang: 源语言代码，可选。
            context_config: 一个从上下文（context）中提取并验证过的配置字典。
                            子类可以直接使用其中的值，无需再次解析 `BaseContextModel`。

        返回:
            一个 `EngineBatchItemResult` 对象 (EngineSuccess 或 EngineError)。
        """
        ...

    def _get_context_config(self, context: Optional[BaseContextModel]) -> dict[str, Any]:
        """
        [私有] 从上下文模型中提取非 None 的值，形成一个配置字典。
        """
        if context and isinstance(context, self.CONTEXT_MODEL):
            # model_dump(exclude_unset=True) 只包含显式设置的字段
            return context.model_dump(exclude_unset=True)
        return {}

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """
        [异步] [最终实现] 批量翻译一组文本。

        此方法是最终的、提供给外部（Coordinator）的接口。它负责：
        1. 验证源语言（如果需要）。
        2. 解析上下文（context）并提取配置。
        3. 创建并并发执行所有单个文本的翻译任务。
        4. 确保返回结果的顺序与输入一致。
        """
        from trans_hub.types import EngineError # 延迟导入以避免循环依赖

        if self.REQUIRES_SOURCE_LANG and not source_lang:
            error_msg = f"引擎 '{self.__class__.__name__}' 需要提供源语言。"
            return [EngineError(error_message=error_msg, is_retryable=False)] * len(texts)

        # 统一解析上下文
        context_config = self._get_context_config(context)

        # 创建并发任务
        tasks = [
            self._atranslate_one(text, target_lang, source_lang, context_config)
            for text in texts
        ]
        
        # 并发执行并收集结果
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理 gather 可能抛出的异常，确保返回 EngineError
        final_results: list[EngineBatchItemResult] = []
        for res in results:
            if isinstance(res, Exception):
                final_results.append(EngineError(error_message=str(res), is_retryable=True))
            else:
                final_results.append(res)
        
        return final_results