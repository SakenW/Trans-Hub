# packages/server/src/trans_hub/application/processors.py
"""
包含处理翻译任务的核心逻辑单元（处理器）。 (UoW 架构版)
"""

import asyncio
from typing import TYPE_CHECKING

import structlog
from trans_hub.domain import tm as tm_domain
from trans_hub_core.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationStatus,
)

if TYPE_CHECKING:
    from trans_hub.adapters.engines.base import BaseTranslationEngine
    from trans_hub_core.interfaces import StreamProducer
    from trans_hub_core.uow import IUnitOfWork

logger = structlog.get_logger(__name__)


class TranslationProcessor:
    """
    负责处理一批翻译任务的默认策略。
    它现在是无状态的，在给定的 UoW 上下文中操作。
    """

    PAYLOAD_TEXT_KEY = "text"

    def __init__(
        self,
        stream_producer: "StreamProducer | None",
        event_stream_name: str,
    ):
        self._stream_producer = stream_producer
        self._event_stream_name = event_stream_name

    async def process_batch(
        self,
        uow: "IUnitOfWork",
        batch: list[ContentItem],
        active_engine: "BaseTranslationEngine",
    ) -> None:
        """
        在给定的 UoW 中处理一批待翻译的内容条目。
        """
        if not batch:
            return

        texts = [item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in batch]
        item_template = batch[0]
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        success_tasks = []
        for item, output in zip(batch, engine_outputs):
            if isinstance(output, EngineSuccess):
                success_tasks.append(
                    self._handle_success(uow, item, output, active_engine)
                )
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
        uow: "IUnitOfWork",
        item: ContentItem,
        output: EngineSuccess,
        active_engine: "BaseTranslationEngine",
    ) -> None:
        """在给定的 UoW 中处理单个翻译成功的结果。"""
        try:
            translated_payload = dict(item.source_payload)
            translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

            new_rev_id = await uow.translations.create_revision(
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

            source_text_for_tm = item.source_payload.get(self.PAYLOAD_TEXT_KEY, "")
            source_fields = {
                "text": tm_domain.normalize_text_for_tm(source_text_for_tm)
            }
            reuse_sha = tm_domain.build_reuse_key(
                namespace=item.namespace, reduced_keys={}, source_fields=source_fields
            )

            tm_id = await uow.tm.upsert_entry(
                project_id=item.project_id,
                namespace=item.namespace,
                src_hash=reuse_sha,
                src_lang=item.source_lang or "auto",
                tgt_lang=item.target_lang,
                variant_key=item.variant_key,
                src_payload=source_fields,
                tgt_payload=translated_payload,
                approved=True,
            )
            await uow.tm.link_revision_to_tm(new_rev_id, tm_id, item.project_id)

        except Exception:
            logger.error(
                "保存成功翻译结果到数据库时失败", head_id=item.head_id, exc_info=True
            )
            # UoW 将自动回滚这个失败的条目
