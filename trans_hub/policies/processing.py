# trans_hub/policies/processing.py
"""本模块定义并实现了白皮书 v1.2 下的翻译处理策略。"""
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

        tasks_to_gather = []
        for item, output in zip(batch, engine_outputs):
            if isinstance(output, EngineSuccess):
                task = asyncio.create_task(self._handle_success(item, output, p_context, active_engine))
                tasks_to_gather.append(task)
            elif isinstance(output, EngineError):
                logger.error(
                    "Engine failed to translate item, it will be retried later.",
                    translation_id=item.translation_id,
                    error=output.error_message,
                    is_retryable=output.is_retryable,
                )

        if not tasks_to_gather:
            return []

        # 并发处理所有成功的任务
        results = await asyncio.gather(*tasks_to_gather)
        return [res for res in results if res is not None]

    async def _handle_success(
        self,
        item: ContentItem,
        output: EngineSuccess,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> TranslationResult | None:
        try:
            # 1. 构建翻译后的 payload
            translated_payload = dict(item.source_payload)
            translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

            # 2. 构建 TM 复用键
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
            
            # 3. 幂等地将新翻译写入 TM
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
            
            # 4. 更新翻译记录为 'reviewed'
            await p_context.handler.update_translation(
                translation_id=item.translation_id,
                status=TranslationStatus.REVIEWED,
                translated_payload=translated_payload,
                tm_id=tm_id,
                engine_name=active_engine.name,
                engine_version=active_engine.VERSION,
            )
            
            # 5. 建立追溯链接
            await p_context.handler.link_translation_to_tm(item.translation_id, tm_id)
            
            return TranslationResult(
                translation_id=item.translation_id,
                content_id=item.content_id,
                status=TranslationStatus.REVIEWED,
                translated_payload=translated_payload,
                engine_name=active_engine.name,
                engine_version=active_engine.VERSION,
            )
        except Exception:
            logger.error("Failed to handle successful translation result in DB", exc_info=True)
            return None