"""trans_hub/engines/translators_engine.py (v1.0)

提供一个使用 `translators` 库的免费翻译引擎。
此版本与泛型 `BaseTranslationEngine` 接口兼容，并修复了 `atranslate_batch` 签名。
"""

import logging  # 导入 logging 模块
from typing import Optional

# 使用 try-except 来处理可选依赖，如果未安装则不加载
try:
    import translators as ts
except ImportError:
    ts = None
    # 可以在此处添加一个警告，但在实际使用时，如果没有安装，初始化时会直接抛出 ImportError
    # logging.warning("Translators library not found. TranslatorsEngine will not be available.")


# 导入基类和相关模型，确保 BaseEngineConfig 已导入
from trans_hub.engines.base import (
    BaseContextModel,
    BaseEngineConfig,
    BaseTranslationEngine,
)

# 导入 EngineBatchItemResult
from trans_hub.types import EngineBatchItemResult, EngineError, EngineSuccess

# 初始化日志记录器
logger = logging.getLogger(__name__)


class TranslatorsEngineConfig(BaseEngineConfig):
    """translators 引擎的特定配置模型。"""

    # 允许用户指定优先使用的翻译服务，如 'google', 'bing'
    provider: str = "google"


# 核心修复：将 TranslatorsEngine 声明为 BaseTranslationEngine 的泛型子类
class TranslatorsEngine(BaseTranslationEngine[TranslatorsEngineConfig]):
    """一个使用 `translators` 库提供免费翻译的引擎。
    这是一个很好的默认或备用引擎，因为它无需 API Key 即可工作。
    """

    CONFIG_MODEL = TranslatorsEngineConfig  # 指定具体的配置模型
    VERSION = "1.0.0"

    def __init__(self, config: TranslatorsEngineConfig):
        """
        初始化 TranslatorsEngine 实例。
        设置翻译服务提供商，并检查 `translators` 库是否已安装。
        Args:
            config: TranslatorsEngineConfig 配置对象。
        """
        # Mypy 现在能够正确识别 self.config 的类型为 TranslatorsEngineConfig
        super().__init__(config)
        if ts is None:
            # 如果 `translators` 库未安装，则在初始化时抛出错误
            raise ImportError(
                "要使用 TranslatorsEngine，请先安装 'translators' 库: pip install translators"
            )
        # 现在 Mypy 知道 self.config 有 provider 属性
        self.provider = self.config.provider

    def translate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """
        批量翻译文本内容。

        使用指定的翻译服务将输入文本列表翻译为目标语言。
        若未提供源语言，默认自动检测。

        参数:
            texts (List[str]): 需要翻译的文本列表。
            target_lang (str): 目标语言代码，例如 'en' 或 'zh-CN'。
            source_lang (Optional[str]): 源语言代码，默认为自动检测。
            context (Optional[BaseContextModel]): 上下文信息，当前未使用。

        返回:
            List[EngineBatchItemResult]: 包含翻译结果或错误信息的结果列表。
        """
        return [self._translate_single(text, target_lang, source_lang) for text in texts]

    def _translate_single(
        self, text: str, target_lang: str, source_lang: Optional[str]
    ) -> EngineBatchItemResult:
        """翻译单个文本的辅助方法"""
        try:
            translated_text = ts.translate_text(
                query_text=text,
                translator=self.provider,
                from_language=source_lang or "auto",
                to_language=target_lang,
            )
            return EngineSuccess(translated_text=translated_text)
        except Exception as e:
            logger.error(
                f"TranslatorsEngine encountered an error for text '{text}': {e}",
                exc_info=True,
            )
            return EngineError(
                error_message=f"Translators lib error: {e}", is_retryable=True
            )

    async def atranslate_batch(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: Optional[str] = None,
        context: Optional[BaseContextModel] = None,
    ) -> list[EngineBatchItemResult]:
        """异步版本的批量翻译，使用线程池执行器并发处理文本"""
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                None, self._translate_single, text, target_lang, source_lang
            )
            for text in texts
        ]
        return await asyncio.gather(*tasks)
