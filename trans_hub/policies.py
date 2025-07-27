# trans_hub/policies.py
"""
本模块定义并实现了具体的翻译处理策略。

它包含策略的接口协议（ProcessingPolicy）及其默认实现（DefaultProcessingPolicy）。
每个策略都封装了一套完整的业务逻辑，用于处理一批待翻译任务。
"""

import asyncio
from typing import Optional, Protocol, Union

import structlog

from trans_hub.context import ProcessingContext
from trans_hub.engines.base import BaseContextModel
from trans_hub.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)

logger = structlog.get_logger(__name__)


class ProcessingPolicy(Protocol):
    """
    定义了翻译任务批处理策略的接口协议。

    它封装了处理一批待翻译项的所有复杂逻辑，如缓存、重试、错误处理等。
    """

    async def process_batch(
        self,
        batch: list[ContentItem],
        target_lang: str,
        context: ProcessingContext,
    ) -> list[TranslationResult]:
        """
        处理一个批次的待翻译内容项。

        参数:
            batch: 从数据库获取的、具有相同上下文的待翻译内容项列表。
            target_lang: 目标翻译语言。
            context: 包含所有必要依赖项的处理上下文“工具箱”。

        返回:
            一个包含所有处理结果（成功或失败）的 `TranslationResult` 列表。
        """
        ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """
    默认的翻译处理策略。

    实现了包含缓存、指数退避重试和详细错误处理的标准工作流。
    """

    async def process_batch(
        self,
        batch: list[ContentItem],
        target_lang: str,
        context: ProcessingContext,
    ) -> list[TranslationResult]:
        """对一个具有相同上下文的批次应用完整的翻译和重试逻辑。"""
        retry_policy = context.config.retry_policy
        return await self._process_batch_with_retry_logic(
            batch,
            target_lang,
            context,
            max_retries=retry_policy.max_attempts,
            initial_backoff=retry_policy.initial_backoff,
        )

    async def _process_batch_with_retry_logic(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        max_retries: int,
        initial_backoff: float,
    ) -> list[TranslationResult]:
        """[私有] 对批次应用完整的翻译和重试逻辑。"""
        business_id_map = await self._get_business_id_map(batch, p_context)
        active_engine = p_context.active_engine

        validated_engine_context = active_engine.validate_and_parse_context(
            batch[0].context if batch else None
        )

        if isinstance(validated_engine_context, EngineError):
            logger.warning(
                "批次上下文验证失败", error=validated_engine_context.error_message
            )
            return [
                self._build_translation_result(
                    item,
                    target_lang,
                    p_context,
                    business_id_map,
                    error_override=validated_engine_context,
                )
                for item in batch
            ]

        items_to_process = list(batch)
        final_results: list[TranslationResult] = []

        for attempt in range(max_retries + 1):
            (
                processed_results,
                retryable_items,
            ) = await self._process_single_translation_attempt(
                items_to_process,
                target_lang,
                p_context,
                business_id_map,
                validated_engine_context,
            )
            final_results.extend(processed_results)

            if not retryable_items:
                return final_results

            if attempt >= max_retries:
                logger.error(
                    "小组达到最大重试次数", retry_item_count=len(retryable_items)
                )
                error = EngineError(
                    error_message="达到最大重试次数", is_retryable=False
                )
                failed_results = [
                    self._build_translation_result(
                        item,
                        target_lang,
                        p_context,
                        business_id_map,
                        error_override=error,
                    )
                    for item in retryable_items
                ]
                final_results.extend(failed_results)
                return final_results

            items_to_process = retryable_items
            backoff_time = initial_backoff * (2**attempt)
            logger.warning(
                f"小组中包含可重试错误，将在 {backoff_time:.2f}s 后重试。",
                retry_count=len(items_to_process),
            )
            await asyncio.sleep(backoff_time)
        return final_results

    async def _process_single_translation_attempt(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        business_id_map: dict[tuple[int, str], Optional[str]],
        engine_context: Optional[BaseContextModel],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 执行单次翻译尝试，分离出成功、失败和可重试的项。"""
        cached_results, uncached_items = await self._separate_cached_items(
            batch, target_lang, p_context, business_id_map
        )
        if not uncached_items:
            return cached_results, []

        engine_outputs = await self._translate_uncached_items(
            uncached_items, target_lang, p_context, engine_context
        )
        processed_results: list[TranslationResult] = list(cached_results)
        retryable_items: list[ContentItem] = []

        for item, output in zip(uncached_items, engine_outputs):
            if isinstance(output, EngineError) and output.is_retryable:
                retryable_items.append(item)
            else:
                result = self._build_translation_result(
                    item, target_lang, p_context, business_id_map, engine_output=output
                )
                processed_results.append(result)

        await self._cache_new_results(processed_results, target_lang, p_context)
        return processed_results, retryable_items

    async def _get_business_id_map(
        self, batch: list[ContentItem], p_context: ProcessingContext
    ) -> dict[tuple[int, str], Optional[str]]:
        """[私有] 批量获取一批内容项对应的业务ID。"""
        if not batch:
            return {}
        tasks = [
            p_context.handler.get_business_id_for_content(
                item.content_id, item.context_hash
            )
            for item in batch
        ]
        return {
            (item.content_id, item.context_hash): biz_id
            for item, biz_id in zip(batch, await asyncio.gather(*tasks))
        }

    async def _separate_cached_items(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        business_id_map: dict,
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 从批处理中分离出已缓存和未缓存的项。"""
        cached_results: list[TranslationResult] = []
        uncached_items: list[ContentItem] = []
        for item in batch:
            request = TranslationRequest(
                source_text=item.value,
                source_lang=p_context.config.source_lang,
                target_lang=target_lang,
                context_hash=item.context_hash,
            )
            cached_text = await p_context.cache.get_cached_result(request)
            if cached_text:
                result = self._build_translation_result(
                    item,
                    target_lang,
                    p_context,
                    business_id_map,
                    cached_text=cached_text,
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
        engine_context: Optional[BaseContextModel],
    ) -> list[Union[EngineSuccess, EngineError]]:
        """[私有] 调用活动引擎翻译一批未缓存的项。"""
        if p_context.rate_limiter:
            await p_context.rate_limiter.acquire(len(items))
        try:
            return await p_context.active_engine.atranslate_batch(
                texts=[item.value for item in items],
                target_lang=target_lang,
                source_lang=p_context.config.source_lang,
                context=engine_context,
            )
        except Exception as e:
            logger.error("引擎调用失败", error=str(e), exc_info=True)
            return [EngineError(error_message=str(e), is_retryable=True)] * len(items)

    async def _cache_new_results(
        self,
        results: list[TranslationResult],
        target_lang: str,
        p_context: ProcessingContext,
    ) -> None:
        """[私有] 将新获得的成功翻译结果存入缓存。"""
        tasks = [
            p_context.cache.cache_translation_result(
                TranslationRequest(
                    source_text=res.original_content,
                    source_lang=p_context.config.source_lang,
                    target_lang=target_lang,
                    context_hash=res.context_hash,
                ),
                res.translated_content or "",
            )
            for res in results
            if res.status == TranslationStatus.TRANSLATED and not res.from_cache
        ]
        if tasks:
            await asyncio.gather(*tasks)

    def _build_translation_result(
        self,
        item: ContentItem,
        target_lang: str,
        p_context: ProcessingContext,
        business_id_map: dict[tuple[int, str], Optional[str]],
        *,
        engine_output: Optional[Union[EngineSuccess, EngineError]] = None,
        cached_text: Optional[str] = None,
        error_override: Optional[EngineError] = None,
    ) -> TranslationResult:
        """[私有] 根据不同的输入源构建一个标准的 `TranslationResult` 对象。"""
        active_engine_name = p_context.config.active_engine
        biz_id = business_id_map.get((item.content_id, item.context_hash))
        final_error = error_override or (
            engine_output if isinstance(engine_output, EngineError) else None
        )
        if final_error:
            return TranslationResult(
                original_content=item.value,
                translated_content=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=active_engine_name,
                error=final_error.error_message,
                from_cache=False,
                context_hash=item.context_hash,
                business_id=biz_id,
            )
        if cached_text is not None:
            return TranslationResult(
                original_content=item.value,
                translated_content=cached_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                from_cache=True,
                engine=f"{active_engine_name} (mem-cached)",
                context_hash=item.context_hash,
                business_id=biz_id,
            )
        if isinstance(engine_output, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_output.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=active_engine_name,
                from_cache=engine_output.from_cache,
                context_hash=item.context_hash,
                business_id=biz_id,
            )
        raise TypeError("无法为项目构建 TranslationResult：输入参数无效。")
