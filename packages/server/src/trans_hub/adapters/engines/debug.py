# packages/server/src/trans_hub/adapters/engines/debug.py
"""
提供一个用于开发和测试的调试翻译引擎。
"""

import asyncio  # [修复] 导入 asyncio

from trans_hub.config import DebugEngineSettings
from trans_hub_core.types import EngineBatchItemResult, EngineError, EngineSuccess

from .base import BaseTranslationEngine


class DebugEngine(BaseTranslationEngine[DebugEngineSettings]):
    """一个简单的调试翻译引擎实现。"""

    CONFIG_MODEL = DebugEngineSettings

    async def _translate(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[EngineBatchItemResult]:
        """
        [最终修复] 修复 "different loop" 错误。

        根本原因：一个没有 `await` 的 `async def` 方法是一个“伪异步”函数，
        它可能会在 SQLAlchemy 的 greenlet 并发模型中导致上下文混乱，
        从而破坏底层 asyncpg 连接与事件循环的绑定。

        解决方案：通过加入 `await asyncio.sleep(0)`，我们强制进行一次
        事件循环的上下文切换。这向 SQLAlchemy 和 asyncio 发出了明确的信号，
        表明这是一个真正的异步操作点，从而保持了 greenlet 和事件循环
        状态的同步，避免了连接状态的破坏。
        """
        await asyncio.sleep(0)

        results = []
        for text in texts:
            if self.config.mode == "FAIL" or text == self.config.fail_on_text:
                results.append(
                    EngineError(
                        error_message="Debug engine forced to fail",
                        is_retryable=self.config.fail_is_retryable,
                    )
                )
                continue

            results.append(
                EngineSuccess(translated_text=f"Translated({text}) to {target_lang}")
            )
        return results
