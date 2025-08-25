# packages/server/tests/helpers/tools/fakes.py
"""
提供测试替身 (Test Doubles)，如 FakeEngine, FakeCache 等。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from trans_hub.adapters.engines.base import (
    BaseEngineConfig,
    BaseTranslationEngine,
)
from trans_hub_core.interfaces import StreamProducer
from trans_hub_core.types import EngineBatchItemResult, EngineError, EngineSuccess


class FakeEngineConfig(BaseEngineConfig):
    """FakeEngine 的配置模型。"""

    mode: str = "success"
    fail_on_text: str | None = None


class FakeTranslationEngine(BaseTranslationEngine[FakeEngineConfig]):
    """
    一个用于测试的可预测的假翻译引擎。
    """

    CONFIG_MODEL = FakeEngineConfig
    VERSION = "0.1.0-fake"

    async def _translate(
        self, texts: list[str], target_lang: str, source_lang: str
    ) -> list[EngineBatchItemResult]:
        results: list[EngineBatchItemResult] = []
        for text in texts:
            if self.config.mode == "fail" or text == self.config.fail_on_text:
                results.append(
                    EngineError(error_message="Fake engine failed", is_retryable=True)
                )
                continue

            results.append(
                EngineSuccess(translated_text=f"Translated('{text}') to {target_lang}")
            )
        return results


class FakeStreamProducer(StreamProducer):
    """一个用于测试的、在内存中记录事件的假事件流生产者。"""

    def __init__(self):
        self.published_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.call_count = 0
        self.fail_on_event_ids: set[str] = set()
        self.fail_on_topics: set[str] = set()

    async def publish(self, stream_name: str, event_data: dict[str, Any]) -> None:
        """记录发布的事件，或根据配置模拟失败。"""
        self.call_count += 1
        
        # 检查是否应该模拟失败
        event_id = event_data.get("id")
        if stream_name in self.fail_on_topics or event_id in self.fail_on_event_ids:
            raise RuntimeError(f"模拟发布失败: stream={stream_name}, event_id={event_id}")
        
        self.published_events[stream_name].append(event_data)

    def set_fail_on_event_ids(self, event_ids: set[str]) -> None:
        """设置应该失败的事件 ID。"""
        self.fail_on_event_ids = event_ids

    def set_fail_on_topics(self, topics: set[str]) -> None:
        """设置应该失败的主题。"""
        self.fail_on_topics = topics

    def clear(self):
        """清空所有记录的事件和失败配置。"""
        self.published_events.clear()
        self.call_count = 0
        self.fail_on_event_ids.clear()
        self.fail_on_topics.clear()
