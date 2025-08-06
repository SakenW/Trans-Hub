# trans_hub/policies/processing.py
"""
本模块定义并实现了具体的翻译处理策略。
v3.0.0 重大更新：适配结构化载荷（payload）和新的核心类型。
"""

import asyncio
from typing import Any, Dict, Optional, Protocol, Union

import structlog

from trans_hub.context import ProcessingContext
from trans_hub.core import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.engines.base import BaseContextModel, BaseTranslationEngine
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class ProcessingPolicy(Protocol):
    """定义了翻译任务批处理策略的接口协议。"""

    async def process_batch(
        self,
        batch: list[ContentItem],
        target_lang: str,
        context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        """
        异步处理一批翻译任务。

        Args:
            batch (list[ContentItem]): 从持久化层获取的待处理内容项列表。
            target_lang (str): 目标语言代码。
            context (ProcessingContext): 包含所有依赖项的处理上下文。
            active_engine (BaseTranslationEngine[Any]): 当前活动的翻译引擎实例。

        Returns:
            list[TranslationResult]: 处理后的一批翻译结果。

        """
        ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """默认的翻译处理策略,实现了包含缓存、重试和DLQ的完整工作流。"""

    PAYLOAD_TEXT_KEY = "text"

    async def process_batch(
        self,
        batch: list[ContentItem],
        target_lang: str,
        context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> list[TranslationResult]:
        retry_policy = context.config.retry_policy
        return await self._process_batch_with_retry_logic(
            batch,
            target_lang,
            context,
            active_engine,
            max_retries=retry_policy.max_attempts,
            initial_backoff=retry_policy.initial_backoff,
            max_backoff=retry_policy.max_backoff,
        )

    async def _process_batch_with_retry_logic(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
        max_retries: int,
        initial_backoff: float,
        max_backoff: float,
    ) -> list[TranslationResult]:
        """[私有] 对批次应用完整的翻译、重试和DLQ逻辑。"""
        validated_engine_context: Union[BaseContextModel, EngineError, None]
        if active_engine.ACCEPTS_CONTEXT:
            raw_context_dict = batch[0].context if batch else None
            parsed_context_or_error = active_engine.validate_and_parse_context(
                raw_context_dict
            )
            if isinstance(parsed_context_or_error, EngineError):
                logger.warning(
                    "批次上下文验证失败", error=parsed_context_or_error.error_message
                )
                return [
                    self._build_translation_result(
                        item,
                        target_lang,
                        p_context,
                        error_override=parsed_context_or_error,
                    )
                    for item in batch
                ]
            validated_engine_context = parsed_context_or_error
        else:
            validated_engine_context = None

        items_to_process = list(batch)
        final_results: list[TranslationResult] = []
        dlq_tasks: list[asyncio.Task[None]] = []

        for attempt in range(max_retries + 1):
            if not items_to_process:
                break

            (
                processed_results,
                retryable_items,
            ) = await self._process_single_translation_attempt(
                items_to_process,
                target_lang,
                p_context,
                active_engine,
                validated_engine_context,
            )
            final_results.extend(processed_results)

            if not retryable_items:
                break

            if attempt >= max_retries:
                logger.error(
                    "任务达到最大重试次数，将移至死信队列", count=len(retryable_items)
                )
                error_message = "达到最大重试次数"
                for item in retryable_items:
                    task = p_context.handler.move_to_dlq(
                        item=item,
                        target_lang=target_lang,
                        error_message=error_message,
                        engine_name=p_context.config.active_engine.value,
                        engine_version=active_engine.VERSION,
                    )
                    dlq_tasks.append(asyncio.create_task(task))
                break

            items_to_process = retryable_items
            backoff_time = min(initial_backoff * (2**attempt), max_backoff)
            logger.warning(
                f"小组中包含可重试错误，将在 {backoff_time:.2f}s 后重试。",
                retry_count=len(items_to_process),
            )
            await asyncio.sleep(backoff_time)

        if dlq_tasks:
            await asyncio.gather(*dlq_tasks)
        return final_results

    async def _process_single_translation_attempt(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
        engine_context: Optional[BaseContextModel],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 执行单次翻译尝试，分离出成功、失败和可重试的项。"""
        cached_results, uncached_items = await self._separate_cached_items(
            batch, target_lang, p_context
        )
        if not uncached_items:
            return cached_results, []

        engine_outputs = await self._translate_uncached_items(
            uncached_items, target_lang, p_context, active_engine, engine_context
        )

        # v3.x 修复：增加对引擎返回数量的严格校验，防止任务静默丢失
        if len(engine_outputs) != len(uncached_items):
            error_msg = (
                f"引擎返回结果数量 ({len(engine_outputs)}) "
                f"与输入数量 ({len(uncached_items)}) 不匹配。"
            )
            logger.error(
                error_msg,
                engine=p_context.config.active_engine.value,
                lang=target_lang,
            )
            engine_error = EngineError(error_message=error_msg, is_retryable=False)
            failed_results = [
                self._build_translation_result(
                    item, target_lang, p_context, engine_output=engine_error
                )
                for item in uncached_items
            ]
            return cached_results + failed_results, []

        processed_results: list[TranslationResult] = list(cached_results)
        retryable_items: list[ContentItem] = []
        item_map = {item.translation_id: item for item in batch}

        for item, output in zip(uncached_items, engine_outputs):
            if isinstance(output, EngineError) and output.is_retryable:
                retryable_items.append(item)
            else:
                result = self._build_translation_result(
                    item, target_lang, p_context, engine_output=output
                )
                processed_results.append(result)

        await self._cache_new_results(processed_results, p_context, item_map)
        return processed_results, retryable_items

    async def _separate_cached_items(
        self, batch: list[ContentItem], target_lang: str, p_context: ProcessingContext
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 从批处理中分离出已缓存和未缓存的项。"""
        cached_results: list[TranslationResult] = []
        uncached_items: list[ContentItem] = []
        for item in batch:
            request = TranslationRequest(
                source_payload=item.source_payload,
                source_lang=item.source_lang or p_context.config.source_lang,
                target_lang=target_lang,
                context_hash=get_context_hash(item.context),
            )
            cached_text = await p_context.cache.get_cached_result(request)
            if cached_text is not None:
                result = self._build_translation_result(
                    item, target_lang, p_context, cached_text=cached_text
                )
                cached_results.append(result)
            else:
                uncached_items.append(item)
        return cached_results, uncached_items

    async def _translate_uncached_items(
        self,
        items: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
        engine_context: Optional[BaseContextModel],
    ) -> list[Union[EngineSuccess, EngineError]]:
        """[私有] 调用活动引擎翻译一批未缓存的项。"""
        texts_to_translate = [
            item.source_payload.get(self.PAYLOAD_TEXT_KEY, "") for item in items
        ]

        source_langs = {item.source_lang for item in items}
        if len(source_langs) == 1:
            batch_source_lang = source_langs.pop() or p_context.config.source_lang
        else:
            logger.warning(
                "批次中包含多种源语言，将回退到全局源语言配置。",
                found_langs=list(source_langs),
            )
            batch_source_lang = p_context.config.source_lang

        return await active_engine.atranslate_batch(
            texts=texts_to_translate,
            target_lang=target_lang,
            source_lang=batch_source_lang,
            context=engine_context,
        )

    async def _cache_new_results(
        self,
        results: list[TranslationResult],
        p_context: ProcessingContext,
        item_map: Dict[str, ContentItem],
    ) -> None:
        """[私有] 将新获得的成功翻译结果存入缓存。"""
        tasks = []
        for res in results:
            if (
                res.status == TranslationStatus.TRANSLATED
                and not res.from_cache
                and res.translated_payload is not None
            ):
                original_item = item_map.get(res.translation_id)
                if not original_item:
                    continue

                request = TranslationRequest(
                    source_payload=res.original_payload,
                    source_lang=original_item.source_lang
                    or p_context.config.source_lang,
                    target_lang=res.target_lang,
                    context_hash=res.context_hash,
                )
                if self.PAYLOAD_TEXT_KEY in res.translated_payload:
                    translated_text = res.translated_payload[self.PAYLOAD_TEXT_KEY]
                    tasks.append(
                        p_context.cache.cache_translation_result(
                            request, str(translated_text)
                        )
                    )
        if tasks:
            await asyncio.gather(*tasks)

    def _build_translation_result(
        self,
        item: ContentItem,
        target_lang: str,
        p_context: ProcessingContext,
        *,
        engine_output: Optional[Union[EngineSuccess, EngineError]] = None,
        cached_text: Optional[str] = None,
        error_override: Optional[EngineError] = None,
    ) -> TranslationResult:
        """[私有] 根据不同的输入源构建一个标准的 `TranslationResult` 对象。"""
        active_engine_name = p_context.config.active_engine.value
        context_hash = get_context_hash(item.context)
        final_error = error_override or (
            engine_output if isinstance(engine_output, EngineError) else None
        )

        if final_error:
            return TranslationResult(
                translation_id=item.translation_id,
                original_payload=item.source_payload,
                translated_payload=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=active_engine_name,
                error=final_error.error_message,
                from_cache=False,
                context_hash=context_hash,
                business_id=item.business_id,
            )

        translated_text: Optional[str] = None
        from_cache = False
        if cached_text is not None:
            translated_text = cached_text
            from_cache = True
            engine = f"{active_engine_name} (mem-cached)"
        elif isinstance(engine_output, EngineSuccess):
            translated_text = engine_output.translated_text
            from_cache = engine_output.from_cache
            engine = active_engine_name
        else:
            raise TypeError("无法为项目构建 TranslationResult：输入参数无效。")

        translated_payload = dict(item.source_payload)
        translated_payload[self.PAYLOAD_TEXT_KEY] = translated_text

        return TranslationResult(
            translation_id=item.translation_id,
            original_payload=item.source_payload,
            translated_payload=translated_payload,
            target_lang=target_lang,
            status=TranslationStatus.TRANSLATED,
            engine=engine,
            from_cache=from_cache,
            context_hash=context_hash,
            business_id=item.business_id,
        )
