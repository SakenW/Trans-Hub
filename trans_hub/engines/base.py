"""
trans_hub/engines/base.py

本模块定义了所有翻译引擎插件必须继承的抽象基类（ABC）。
它规定了引擎的配置模型、上下文模型以及核心的翻译方法接口。
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Type

from pydantic import BaseModel

from trans_hub.types import EngineBatchItemResult

# ==============================================================================
#  基础模型定义
# ==============================================================================

class BaseContextModel(BaseModel):
    """
    所有引擎特定上下文模型的基类。
    默认情况下，它是一个空的 Pydantic 模型，表示引擎不需要任何特定上下文。
    第三方引擎开发者应从此模型继承，以定义他们自己的上下文数据结构。
    """
    pass


class BaseEngineConfig(BaseModel):
    """
    所有引擎配置模型的基类。
    它包含了一些通用的速率限制配置，具体引擎可以扩展此模型以添加自己的配置项，
    例如 API 密钥、区域终结点等。
    """
    # 每分钟请求数限制
    rpm: Optional[int] = None
    # 每秒请求数限制
    rps: Optional[int] = None
    # 最大并发连接数
    max_concurrency: Optional[int] = None


# ==============================================================================
#  抽象引擎基类
# ==============================================================================

class BaseTranslationEngine(ABC):
    """
    翻译引擎的抽象基类。所有具体的翻译引擎实现都必须继承此类。

    核心职责：
    - 只负责单一、无状态的翻译转换逻辑。
    - “无状态”指其 `translate_batch` 方法是可重入的。
    - 引擎实例本身可以持有从配置初始化的长生命周期对象（如 aiohttp.ClientSession）。
    """

    # --- 类属性，用于元数据和契约定义 ---

    # 指定该引擎所使用的配置模型类型。必须是 BaseEngineConfig 的子类。
    # Coordinator 将使用此模型来验证和结构化传入的引擎配置。
    CONFIG_MODEL: Type[BaseEngineConfig]

    # 指定该引擎所使用的上下文模型类型。必须是 BaseContextModel 的子类。
    # Coordinator 将使用此模型来验证和结构化传入的上下文。
    CONTEXT_MODEL: Type[BaseContextModel] = BaseContextModel

    # 引擎的版本号，用于数据持久化和问题追踪。
    VERSION: str = "1.0.0"

    # 标志位，指示此引擎是否必须提供源语言才能进行翻译。
    # 如果为 True，Coordinator 在调用 translate_batch 前会确保源语言可用。
    # 默认为 False，表示引擎可以自行检测源语言。
    REQUIRES_SOURCE_LANG: bool = False

    def __init__(self, config: BaseEngineConfig):
        """
        初始化引擎实例。

        Args:
            config: 一个已经过验证的、与该引擎 CONFIG_MODEL 匹配的配置对象。
        """
        self.config = config

    @abstractmethod
    def translate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """
        批量翻译一组文本。这是一个同步（阻塞）方法。

        重要约束：
        - 返回的列表长度和顺序必须与输入的 `texts` 列表严格一一对应。
        - 即使某个文本翻译失败，也必须在对应位置填充一个 EngineError 对象。

        Args:
            texts: 需要翻译的字符串列表。
            target_lang: 目标语言代码 (例如, 'en', 'zh-CN')。
            source_lang: 源语言代码，可选。如果 `REQUIRES_SOURCE_LANG` 为 True，则此参数必不为 None。
            context: 经过验证的、与该引擎 `CONTEXT_MODEL` 匹配的上下文对象。

        Returns:
            一个 `EngineBatchItemResult` 对象的列表，每个对象对应一个输入文本的翻译结果。
        """
        ...
    
    # 异步版本，供 AsyncCoordinator 使用
    @abstractmethod
    async def atranslate_batch(
        self,
        texts: List[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> List[EngineBatchItemResult]:
        """
        批量翻译一组文本的异步版本。

        约束与同步版本完全相同。

        Args:
            texts: 需要翻译的字符串列表。
            target_lang: 目标语言代码。
            source_lang: 源语言代码，可选。
            context: 经过验证的上下文对象。

        Returns:
            一个 `EngineBatchItemResult` 对象的列表。
        """
        ...