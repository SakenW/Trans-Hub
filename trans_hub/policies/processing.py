# trans_hub/policies/processing.py
# [v2.4 Refactor] 更新处理策略以适配 rev/head 模型。
# 成功翻译后，创建新的 'reviewed' 修订，并更新头表指针。
import asyncio
from typing import Any, Protocol

import structlog

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.core import (
    ContentItem,
    EngineError,
    EngineSuccess,
    ProcessingContext,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.engines.base import BaseTranslationEngine

logger = structlog.get_logger(__name__)


class ProcessingPolicy(Protocol):
    async def process_batch(
        self,
        batch: list[ContentItem],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]: ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """默认的翻译处理策略（白皮书 v2.4）。"""

    PAYLOAD_TEXT_KEY = "text"

    async def process_batch(
        self,
        batch: list[ContentItem],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        if not batch:
            return []

        texts = [item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in batch]
        # 假设批次内 lang, source_lang 一致
        item_template = batch[0]
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        success_items = []
        for item, output in zip(batch, engine_outputs, strict=False):
            if isinstance(output, EngineSuccess):
                success_items.append((item, output))
            elif isinstance(output, EngineError):
                logger.error(
                    "引擎翻译失败，将等待重试",
                    translation_id=item.translation_id,
                    error=output.error_message,
                )

        if not success_items:
            return []

        # [v2.4] 根据数据库方言选择并发或串行写入
        is_sqlite = p_context.handler._is_sqlite
        if is_sqlite:
            final_results = [
                await self._handle_success(item, out, p_context, active_engine)
                for item, out in success_items
            ]
        else:
            tasks = [
                self._handle_success(item, out, p_context, active_engine)
                for item, out in success_items
            ]
            final_results = await asyncio.gather(*tasks)

        return [res for res in final_results if res is not None]

    async def _handle_success(
        self,
        item: ContentItem,
        output: EngineSuccess,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> TranslationResult | None:
        try:
            # 1. 准备数据
            translated_payload = dict(item.source_payload)
            translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

            # 2. 创建新修订并更新头表
            new_rev_id = await p_context.handler.create_new_translation_revision(
                head_id=item.head_id,
                project_id=item.project_id,
                content_id=item.content_id,
                target_lang=item.target_lang,
                variant_key=item.variant_key,
                status=TranslationStatus.REVIEWED,
                revision_no=item.revision_no + 1,
                translated_payload=translated_payload,
                engine_name=active_engine.name,
                engine_version=active_engine.VERSION,
            )

            # 3. 更新/创建 TM 条目并链接
            source_fields = {
                "text": normalize_plain_text_for_reuse(item.source_payload.get("text"))
            }
            reuse_sha = build_reuse_sha256(
                namespace=item.namespace, reduced_keys={}, source_fields=source_fields
            )
            tm_id = await p_context.handler.upsert_tm_entry(
                project_id=item.project_id,
                namespace=item.namespace,
                reuse_sha256_bytes=reuse_sha,
                source_lang=item.source_lang or "auto",
                target_lang=item.target_lang,
                variant_key=item.variant_key,
                policy_version=1,
                hash_algo_version=1,
                source_text_json=source_fields,
                translated_json=translated_payload,
                quality_score=0.9,
            )
            await p_context.handler.link_translation_to_tm(new_rev_id, tm_id)

            return TranslationResult(
                translation_id=new_rev_id,
                content_id=item.content_id,
                status=TranslationStatus.REVIEWED,
            )
        except Exception:
            logger.error(
                "保存成功翻译结果到数据库失败",
                translation_id=item.translation_id,
                exc_info=True,
            )
            return None
