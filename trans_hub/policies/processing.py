# trans_hub/policies/processing.py
"""本模块定义并实现了 UIDA 架构下的翻译处理策略。"""
import asyncio
from typing import Any, Protocol

import structlog

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.context import ProcessingContext
from trans_hub.core import (
    ContentItem, EngineError, EngineSuccess, TranslationResult, TranslationStatus
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
        """
        处理一批待翻译任务。
        
        Args:
            batch: 从数据库获取的待处理任务列表。
            p_context: 包含配置和持久化处理器的处理上下文。
            active_engine: 当前活动的翻译引擎实例。

        Returns:
            一个包含处理结果的列表，用于回写数据库。
        """
        ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """
    默认的 UIDA 翻译处理策略。
    负责编排“翻译引擎调用 -> 写回 TM -> 更新翻译记录 -> 建立追溯链接”这一核心事务。
    """
    # 定义了在 source_payload 中哪个键包含要翻译的文本
    PAYLOAD_TEXT_KEY = "text"

    async def process_batch(
        self,
        batch: list[ContentItem],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        """
        处理一个批次的翻译任务，对批次内的所有任务调用翻译引擎，
        然后将成功的结果通过事务性操作写回数据库。
        """
        if not batch:
            return []

        # 提取所有待翻译的文本
        texts_to_translate = [
            item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in batch
        ]
        
        # 假设一个批次内的所有任务具有相同的源/目标语言和变体，这由 stream_translatable_items 保证
        item_template = batch[0]
        
        # 异步调用翻译引擎
        engine_outputs = await active_engine.atranslate_batch(
            texts=texts_to_translate,
            target_lang=item_template.target_lang,
            source_lang=item_template.source_lang,
        )

        final_results: list[TranslationResult] = []
        tasks_to_gather = []
        
        # 遍历引擎返回的每一个结果
        for item, output in zip(batch, engine_outputs):
            if isinstance(output, EngineSuccess):
                # 如果翻译成功，创建一个异步任务来处理后续的数据库写入
                task = asyncio.create_task(self._handle_success(item, output, p_context, active_engine))
                tasks_to_gather.append(task)
            elif isinstance(output, EngineError):
                # 如果翻译失败，直接构建一个失败结果
                result = TranslationResult(
                    translation_id=item.translation_id,
                    content_id=item.content_id,
                    status=TranslationStatus.FAILED,
                    error=output.error_message,
                )
                final_results.append(result)

        # 并发执行所有成功的数据库写入任务
        if tasks_to_gather:
            success_results = await asyncio.gather(*tasks_to_gather, return_exceptions=True)
            for res in success_results:
                if isinstance(res, TranslationResult):
                    final_results.append(res)
                elif isinstance(res, Exception):
                    # 如果数据库写入失败，记录错误，但目前不创建 FAILED 状态
                    # 因为任务状态在数据库中仍是 TRANSLATING，下次会被 Worker 重试
                    logger.error("处理成功翻译时发生数据库错误", exc_info=res)
        
        # 将所有结果（成功或失败）批量回写到数据库
        await p_context.handler.save_translation_results(final_results)
        return final_results

    async def _handle_success(
        self,
        item: ContentItem,
        output: EngineSuccess,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> TranslationResult:
        """
        处理单条翻译成功的结果。这是一个原子性的业务流程，
        包括写入 TM、建立追溯链接，并返回一个待审阅状态的结果。
        """
        # 1. 构建翻译后的 payload，保留原文的其他元数据
        translated_payload = dict(item.source_payload)
        translated_payload[self.PAYLOAD_TEXT_KEY] = output.translated_text

        # 2. 构建 TM 复用键
        # 注意: 真实的复用策略应从 namespace_registry.json 加载
        reuse_policy = {"include_source_fields": [self.PAYLOAD_TEXT_KEY]}
        
        source_fields_for_reuse = {
            k: normalize_plain_text_for_reuse(item.source_payload.get(k))
            for k in reuse_policy.get("include_source_fields", [])
        }
        
        # 注意: 真实的降维 keys 逻辑需要从 namespace_registry.json 加载策略
        reduced_keys = {}  # 简化处理
        reuse_sha = build_reuse_sha256(
            namespace=item.namespace,
            reduced_keys=reduced_keys,
            source_fields=source_fields_for_reuse,
        )
        
        # 3. 幂等地将新翻译写入翻译记忆库 (TM)
        tm_id = await p_context.handler.upsert_tm_entry(
            project_id=item.project_id,
            namespace=item.namespace,
            reuse_sha256_bytes=reuse_sha,
            source_lang=item.source_lang or "auto", # 假设需要源语言
            target_lang=item.target_lang,
            variant_key=item.variant_key,
            policy_version=1,  # 简化
            hash_algo_version=1,  # 简化
            source_text_json=source_fields_for_reuse,
            translated_json=translated_payload,
            quality_score=0.9,  # 机器翻译默认质量分
        )
        
        # 4. 建立从当前翻译记录到新 TM 条目的追溯链接
        await p_context.handler.link_translation_to_tm(item.translation_id, tm_id)

        # 5. 构建最终的成功结果对象，状态为“待审阅”
        return TranslationResult(
            translation_id=item.translation_id,
            content_id=item.content_id,
            status=TranslationStatus.REVIEWED,  # 机翻后进入待审状态
            translated_payload=translated_payload,
            engine_name=active_engine.name,
            engine_version=active_engine.VERSION,
        )