# trans_hub/policies/processing.py
"""本模块定义并实现了具体的翻译处理策略。"""

import asyncio
from typing import Any, Optional, Protocol, Union

import structlog

from trans_hub.context import ProcessingContext
from trans_hub.engines.base import BaseContextModel, BaseTranslationEngine
from trans_hub.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)
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
    """默认的翻译处理策略，实现了包含缓存、重试和DLQ的完整工作流。"""

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
        )

    async def _process_batch_with_retry_logic(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
        max_retries: int,
        initial_backoff: float,
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
                        error_message=error_message,
                        engine_name=p_context.config.active_engine.value,
                        engine_version=active_engine.VERSION,
                    )
                    dlq_tasks.append(asyncio.create_task(task))
                break

            items_to_process = retryable_items
            backoff_time = initial_backoff * (2**attempt)
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
        processed_results: list[TranslationResult] = list(cached_results)
        retryable_items: list[ContentItem] = []

        for item, output in zip(uncached_items, engine_outputs):
            if isinstance(output, EngineError) and output.is_retryable:
                retryable_items.append(item)
            else:
                result = self._build_translation_result(
                    item, target_lang, p_context, engine_output=output
                )
                processed_results.append(result)

        await self._cache_new_results(processed_results, p_context)
        return processed_results, retryable_items

    async def _separate_cached_items(
        self, batch: list[ContentItem], target_lang: str, p_context: ProcessingContext
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 从批处理中分离出已缓存和未缓存的项。"""
        cached_results: list[TranslationResult] = []
        uncached_items: list[ContentItem] = []
        for item in batch:
            request = TranslationRequest(
                source_text=item.value,
                source_lang=p_context.config.source_lang,
                target_lang=target_lang,
                context_hash=get_context_hash(item.context),
            )
            cached_text = await p_context.cache.get_cached_result(request)
            if cached_text:
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
        if p_context.rate_limiter:
            await p_context.rate_limiter.acquire(len(items))

        return await active_engine.atranslate_batch(
            texts=[item.value for item in items],
            target_lang=target_lang,
            source_lang=p_context.config.source_lang,
            context=engine_context,
        )

    async def _cache_new_results(
        self, results: list[TranslationResult], p_context: ProcessingContext
    ) -> None:
        """[私有] 将新获得的成功翻译结果存入缓存。"""
        tasks = []
        for res in results:
            if (
                res.status == TranslationStatus.TRANSLATED
                and not res.from_cache
                and res.translated_content
            ):
                request = TranslationRequest(
                    source_text=res.original_content,
                    source_lang=p_context.config.source_lang,
                    target_lang=res.target_lang,
                    context_hash=res.context_hash,
                )
                tasks.append(
                    p_context.cache.cache_translation_result(
                        request, res.translated_content
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
                original_content=item.value,
                translated_content=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=active_engine_name,
                error=final_error.error_message,
                from_cache=False,
                context_hash=context_hash,
                business_id=item.business_id,
            )
        if cached_text is not None:
            return TranslationResult(
                translation_id=item.translation_id,
                original_content=item.value,
                translated_content=cached_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                from_cache=True,
                engine=f"{active_engine_name} (mem-cached)",
                context_hash=context_hash,
                business_id=item.business_id,
            )
        if isinstance(engine_output, EngineSuccess):
            return TranslationResult(
                translation_id=item.translation_id,
                original_content=item.value,
                translated_content=engine_output.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=active_engine_name,
                from_cache=engine_output.from_cache,
                context_hash=context_hash,
                business_id=item.business_id,
            )
        raise TypeError("无法为项目构建 TranslationResult：输入参数无效。")
