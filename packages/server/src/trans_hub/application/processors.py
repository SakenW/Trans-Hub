# packages/server/src/trans_hub/application/processors.py
"""
包含处理翻译任务的核心逻辑单元（处理器）。 (UoW 架构版)
"""

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

        # 验证并过滤有效的文本条目
        valid_items = []
        texts = []
        
        for item in batch:
            text = item.source_payload.get(self.PAYLOAD_TEXT_KEY, "")
            if not text or not text.strip():
                logger.warning(
                    "跳过缺失或空的文本条目",
                    head_id=item.head_id,
                    content_id=item.content_id,
                    payload_keys=list(item.source_payload.keys()),
                )
                continue
            
            valid_items.append(item)
            texts.append(text)
        
        # 如果没有有效的文本条目，直接返回
        if not valid_items:
            logger.info("批次中没有有效的文本条目，跳过翻译")
            return

        item_template = valid_items[0]
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        # 校验引擎返回数量与输入数量是否匹配
        if len(engine_outputs) != len(valid_items):
            logger.error(
                "引擎返回结果数量与输入条目数量不匹配，存在数据丢失风险",
                expected_count=len(valid_items),
                actual_count=len(engine_outputs),
                engine_name=active_engine.name(),
                batch_size=len(batch),
            )
            raise ValueError(
                f"引擎返回结果数量不匹配：期望 {len(valid_items)} 个结果，"
                f"实际收到 {len(engine_outputs)} 个结果"
            )

        for item, output in zip(valid_items, engine_outputs):
            if isinstance(output, EngineSuccess):
                await self._handle_success(uow, item, output, active_engine)
            elif isinstance(output, EngineError):
                logger.error(
                    "引擎翻译失败，将等待重试",
                    head_id=item.head_id,
                    error=output.error_message,
                    is_retryable=output.is_retryable,
                )

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

            # 发布翻译完成事件
            if self._stream_producer and self._event_stream_name:
                event_data = {
                    "event_type": "translation_completed",
                    "head_id": item.head_id,
                    "project_id": item.project_id,
                    "content_id": item.content_id,
                    "target_lang": item.target_lang,
                    "revision_id": new_rev_id,
                    "engine_name": active_engine.name(),
                    "engine_version": active_engine.VERSION,
                }
                try:
                    await self._stream_producer.publish(self._event_stream_name, event_data)
                    logger.debug(
                        "翻译完成事件已发布",
                        head_id=item.head_id,
                        stream=self._event_stream_name,
                    )
                except Exception:
                    logger.warning(
                        "发布翻译完成事件失败，但不影响翻译结果保存",
                        head_id=item.head_id,
                        stream=self._event_stream_name,
                        exc_info=True,
                    )

        except Exception:
            logger.error(
                "保存成功翻译结果到数据库时失败", head_id=item.head_id, exc_info=True
            )
            # 重新抛出异常以确保 UoW 回滚事务
            raise

