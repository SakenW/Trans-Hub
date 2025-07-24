# trans_hub/engines/base.py (重构后)

"""本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。.

它规定了引擎的配置模型、上下文模型以及核心的异步翻译方法接口。
此版本为纯异步设计，强制所有引擎实现 atranslate_batch 方法。
"""

from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

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
#  抽象引擎基类 (重构)
# ==============================================================================


class BaseTranslationEngine(ABC, Generic[_ConfigType]):
    """翻译引擎的纯异步抽象基类。所有引擎实现都必须继承此类。.

    核心职责：
    - 提供单一、无状态的异步翻译转换逻辑。
    - 引擎实例本身可以持有从配置初始化的长生命周期对象（如 aiohttp.ClientSession）。
    """

    # --- 类属性，用于元数据和契约定义 ---

    # 指定该引擎所使用的配置模型类型。
    CONFIG_MODEL: type[_ConfigType]

    # 指定该引擎所使用的上下文模型类型。
    CONTEXT_MODEL: type[BaseContextModel] = BaseContextModel

    # 引擎的版本号，用于数据持久化和问题追踪。
    VERSION: str = "1.0.0"

    # 标志位，指示此引擎是否必须提供源语言才能进行翻译。
    REQUIRES_SOURCE_LANG: bool = False

    # (已移除) IS_ASYNC_ONLY 标志不再需要，因为基类强制异步实现。

    def __init__(self, config: _ConfigType):
        """初始化引擎实例。.

        参数:
            config: 一个已经过验证的、与该引擎 CONFIG_MODEL 匹配的配置对象。
        """
        self.config = config

    # (已移除) 同步的 translate_batch 方法被移除，以强制纯异步设计。
    # @abstractmethod
    # def translate_batch(...) -> ...:
    #     ...

    @abstractmethod
    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """[异步] 批量翻译一组文本。这是所有引擎必须实现的唯一翻译方法。.

        重要约束：
        - 返回的列表长度和顺序必须与输入的 `texts` 列表严格一一对应。
        - 即使某个文本翻译失败，也必须在对应位置填充一个 EngineError 对象。
        - 如果底层库是同步的，实现者应使用 `asyncio.to_thread` 来包装阻塞调用，
          以避免阻塞事件循环。

        参数:
            texts: 需要翻译的字符串列表。
            target_lang: 目标语言代码 (例如, 'en', 'zh-CN')。
            source_lang: 源语言代码，可选。
            context: 经过验证的、与该引擎 `CONTEXT_MODEL` 匹配的上下文对象。

        返回:
            一个 `EngineBatchItemResult` 对象的列表。
        """
        ...
