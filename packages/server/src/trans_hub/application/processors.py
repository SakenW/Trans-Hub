# packages/server/src/trans_hub/application/processors.py
"""
包含处理翻译任务的核心逻辑单元（处理器）。
"""

import asyncio
from typing import Any

import structlog

from trans_hub.domain import tm as tm_domain
from trans_hub_core.interfaces import PersistenceHandler
from trans_hub_core.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationStatus,
)

# from trans_hub.infrastructure.engines.base import BaseTranslationEngine # 避免循环导入
from trans_hub_core.interfaces import StreamProducer

logger = structlog.get_logger(__name__)


class TranslationProcessor:
    """
    负责处理一批翻译任务的默认策略。
    """

    PAYLOAD_TEXT_KEY = "text"

    def __init__(
        self,
        handler: PersistenceHandler,
        stream_producer: StreamProducer | None,
        event_stream_name: str,
    ):
        """
        初始化处理器。

        Args:
            handler: 持久化处理器实例。
            stream_producer: 事件流生产者实例，用于发布事件。
            event_stream_name: 事件流的名称。
        """
        self._handler = handler
        self._stream_producer = stream_producer
        self._event_stream_name = event_stream_name

    async def process_batch(
        self,
        batch: list[ContentItem],
        active_engine: Any,  # BaseTranslationEngine
    ) -> None:
        """
        处理一批待翻译的内容条目。

        流程：
        1. 批量调用翻译引擎。
        2. 对成功的结果，创建新的 "reviewed" 修订。
        3. 更新或创建 TM 条目并建立链接。
        4. 对失败的结果，记录日志（未来的重试逻辑可以在此扩展）。
        """
        if not batch:
            return

        texts = [item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in batch]
        # 假设批次内 lang, source_lang 一致
        item_template = batch[0]
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        success_tasks = []
        for item, output in zip(batch, engine_outputs):
            if isinstance(output, EngineSuccess):
                success_tasks.append(self._handle_success(item, output, active_engine))
            elif isinstance(output, EngineError):
                logger.error(
                    "引擎翻译失败，将等待重试",
                    head_id=item.head_id,
                    error=output.error_message,
                    is_retryable=output.is_retryable,
                )

        if success_tasks:
            await asyncio.gather(*success_tasks)

    async def _handle_success(
        self,
        item: ContentItem,
        output: EngineSuccess,
        active_engine: Any,  # BaseTranslationEngine
    ) -> None:
        """处理单个翻译成功的结果。"""
        try:
            # 1. 准备数据
            translated_payload = dict(item.source_payload)
            translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

            # 2. 创建新修订并更新头表
            new_rev_id = await self._handler.create_new_translation_revision(
                head_id=item.head_id,
                project_id=item.project_id,
                content_id=item.content_id,
                target_lang=item.target_lang,
                variant_key=item.variant_key,
                status=TranslationStatus.REVIEWED,
                revision_no=item.current_no + 1,
                translated_payload_json=translated_payload,
                engine_name=active_engine.name(),
                engine_version=active_engine.VERSION,
            )

            # 3. 更新/创建 TM 条目并链接
            source_text_for_tm = item.source_payload.get(self.PAYLOAD_TEXT_KEY, "")
            source_fields = {
                "text": tm_domain.normalize_text_for_tm(source_text_for_tm)
            }
            reuse_sha = tm_domain.build_reuse_key(
                namespace=item.namespace, reduced_keys={}, source_fields=source_fields
            )

            # [修复] 修正参数名以匹配 ThTmUnits ORM 模型
            tm_id = await self._handler.upsert_tm_entry(
                project_id=item.project_id,
                namespace=item.namespace,
                src_hash=reuse_sha,
                src_lang=item.source_lang or "auto",
                tgt_lang=item.target_lang,
                variant_key=item.variant_key,
                src_payload=source_fields,
                tgt_payload=translated_payload,
                approved=True,  # 机器翻译结果默认为 approved
            )
            await self._handler.link_translation_to_tm(
                new_rev_id, tm_id, item.project_id
            )

        except Exception:
            logger.error(
                "保存成功翻译结果到数据库时失败",
                head_id=item.head_id,
                exc_info=True,
            )