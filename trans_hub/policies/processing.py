# trans_hub/policies/processing.py
# [终极版 v1.8 - 修正 SQLite 并发写入死锁]
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
    """定义了翻译任务批处理策略的接口协议。"""

    async def process_batch(
        self,
        batch: list[ContentItem],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """
    默认的翻译处理策略（白皮书 v1.2）。
    负责编排“翻译引擎调用 -> 写回 TM -> 更新翻译记录为 'reviewed'”这一核心流程。
    失败的任务将被忽略，等待下一轮 Worker 重试。
    """
    PAYLOAD_TEXT_KEY = "text"

    async def process_batch(
        self,
        batch: list[ContentItem],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        if not batch:
            return []

        texts_to_translate = [
            item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in batch
        ]
        item_template = batch[0]
        
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts_to_translate,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        success_items = []
        for item, output in zip(batch, engine_outputs):
            if isinstance(output, EngineSuccess):
                success_items.append((item, output))
            elif isinstance(output, EngineError):
                logger.error(
                    "Engine failed to translate item, it will be retried later.",
                    translation_id=item.translation_id,
                    error=output.error_message,
                    is_retryable=output.is_retryable,
                )

        if not success_items:
            return []

        # [终极修复] 根据数据库方言选择并发或串行写入
        # BasePersistenceHandler 中已经有 _is_sqlite 属性
        is_sqlite = p_context.handler._is_sqlite

        final_results = []
        if is_sqlite:
            # 对于 SQLite，必须串行处理以避免死锁
            logger.debug("Using serial DB write for SQLite.")
            for item, output in success_items:
                result = await self._handle_success(item, output, p_context, active_engine)
                if result:
                    final_results.append(result)
        else:
            # 对于 PostgreSQL，可以使用并发写入以提高性能
            logger.debug("Using concurrent DB write for PostgreSQL.")
            tasks = [
                self._handle_success(item, output, p_context, active_engine)
                for item, output in success_items
            ]
            results = await asyncio.gather(*tasks)
            final_results = [res for res in results if res is not None]
        
        return final_results

    async def _handle_success(
        self,
        item: ContentItem,
        output: EngineSuccess,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> TranslationResult | None:
        try:
            translated_payload = dict(item.source_payload)
            translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

            reuse_policy = {"include_source_fields": [self.PAYLOAD_TEXT_KEY]}
            source_fields_for_reuse = {
                k: normalize_plain_text_for_reuse(item.source_payload.get(k))
                for k in reuse_policy.get("include_source_fields", [])
            }
            reduced_keys = {}
            reuse_sha = build_reuse_sha256(
                namespace=item.namespace,
                reduced_keys=reduced_keys,
                source_fields=source_fields_for_reuse,
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
                source_text_json=source_fields_for_reuse,
                translated_json=translated_payload,
                quality_score=0.9 if not output.from_cache else 1.0,
            )
            
            await p_context.handler.update_translation(
                translation_id=item.translation_id,
                status=TranslationStatus.REVIEWED,
                translated_payload=translated_payload,
                tm_id=tm_id,
                engine_name=active_engine.name,
                engine_version=active_engine.VERSION,
            )
            
            await p_context.handler.link_translation_to_tm(item.translation_id, tm_id)
            
            return TranslationResult(
                translation_id=item.translation_id,
                content_id=item.content_id,
                status=TranslationStatus.REVIEWED,
            )
        except Exception:
            logger.error(
                "Failed to save successful translation result to DB",
                translation_id=item.translation_id,
                exc_info=True
            )
            return None