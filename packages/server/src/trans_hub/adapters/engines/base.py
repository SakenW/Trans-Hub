# packages/server/src/trans_hub/adapters/engines/base.py
"""
定义了所有翻译引擎的抽象基类和通用配置。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel
from trans_hub_core.types import EngineBatchItemResult, EngineError

_ConfigType = TypeVar("_ConfigType", bound="BaseEngineConfig")


class BaseEngineConfig(BaseModel):
    """所有引擎配置模型的基类。"""

    max_batch_size: int = 50


class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类。"""

    CONFIG_MODEL: type[_ConfigType]
    VERSION: str = "1.0.0"

    def __init__(self, config: _ConfigType):
        self.config = config
        self.initialized = False

    @classmethod
    def name(cls) -> str:
        """从类名自动推断引擎的名称。"""
        return cls.__name__.removesuffix("Engine").lower()

    async def initialize(self) -> None:
        """引擎的异步初始化钩子，用于设置连接池等。"""
        self.initialized = True

    async def close(self) -> None:
        """引擎的异步关闭钩子，用于安全释放资源。"""
        self.initialized = False

    @abstractmethod
    async def _translate(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[EngineBatchItemResult]:
        """[子类实现] 真正执行批量翻译的逻辑。"""
        raise NotImplementedError

    async def atranslate_batch(
        self, texts: list[str], target_lang: str, source_lang: str | None
    ) -> list[EngineBatchItemResult]:
        """[公共 API] 异步翻译一批文本。"""
        if not source_lang:
            return [
                EngineError(
                    error_message=f"引擎 '{self.name()}' 需要提供源语言。",
                    is_retryable=False,
                )
            ] * len(texts)

        try:
            return await self._translate(texts, target_lang, source_lang)
        except Exception as e:
            return [
                EngineError(
                    error_message=f"引擎执行时发生未知异常: {e}", is_retryable=True
                )
            ] * len(texts)
