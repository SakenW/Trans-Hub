# trans_hub/policies/processing.py
"""本模块定义并实现了具体的翻译处理策略。"""

import asyncio
from itertools import groupby
from typing import Any, Protocol, Union

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
    ) -> list[TranslationResult]: ...

    def _get_context_hash(self, context: dict[str, Any] | None) -> str: ...


class DefaultProcessingPolicy(ProcessingPolicy):
    """默认的翻译处理策略,实现了包含缓存、重试和DLQ的完整工作流。"""

    PAYLOAD_TEXT_KEY = "text"

    def _get_context_hash(self, context: dict[str, Any] | None) -> str:
        return get_context_hash(context)

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
                dlq_tasks = [
                    asyncio.create_task(
                        p_context.handler.move_to_dlq(
                            item=item,
                            target_lang=target_lang,
                            error_message=error_message,
                            engine_name=p_context.config.active_engine.value,
                            engine_version=active_engine.VERSION,
                        )
                    )
                    for item in retryable_items
                ]
                await asyncio.gather(*dlq_tasks, return_exceptions=True)

                # [核心修复] 为被移入 DLQ 的任务创建并返回 FAILED 结果，
                # 确保调用方（Coordinator）能够收到任务已终结的明确信号。
                dlq_results = [
                    self._build_translation_result(
                        item,
                        target_lang,
                        p_context,
                        error_override=EngineError(
                            error_message=error_message, is_retryable=False
                        ),
                    )
                    for item in retryable_items
                ]
                final_results.extend(dlq_results)
                break  # 确保在处理完DLQ后退出循环

            items_to_process = retryable_items
            backoff_time = min(initial_backoff * (2**attempt), max_backoff)
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
        active_engine: BaseTranslationEngine[Any],
        engine_context: BaseContextModel | None,
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """[私有] 执行单次翻译尝试，分离出成功、失败和可重试的项。"""
        cached_results, uncached_items = await self._separate_cached_items(
            batch, target_lang, p_context, active_engine
        )

        valid_items, payload_error_results = self._validate_payload_structure(
            uncached_items, target_lang, p_context
        )

        if not valid_items:
            return cached_results + payload_error_results, []

        engine_outputs = await self._translate_uncached_items(
            valid_items, target_lang, p_context, active_engine, engine_context
        )

        if len(engine_outputs) != len(valid_items):
            error_msg = (
                f"引擎返回结果数量 ({len(engine_outputs)}) 与输入数量 "
                f"({len(valid_items)}) 不匹配。"
            )
            logger.error(
                error_msg, engine=p_context.config.active_engine.value, lang=target_lang
            )
            engine_error = EngineError(error_message=error_msg, is_retryable=False)
            mismatch_results = [
                self._build_translation_result(
                    item, target_lang, p_context, engine_output=engine_error
                )
                for item in valid_items
            ]
            return cached_results + payload_error_results + mismatch_results, []

        processed_results: list[TranslationResult] = list(cached_results)
        processed_results.extend(payload_error_results)
        retryable_items: list[ContentItem] = []

        for item, output in zip(valid_items, engine_outputs, strict=True):
            if isinstance(output, EngineError) and output.is_retryable:
                retryable_items.append(item)
            else:
                result = self._build_translation_result(
                    item, target_lang, p_context, engine_output=output
                )
                processed_results.append(result)

        await self._cache_new_results(
            processed_results,
            p_context,
            active_engine,
            {item.translation_id: item for item in batch},
        )
        return processed_results, retryable_items

    def _validate_payload_structure(
        self,
        items: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
    ) -> tuple[list[ContentItem], list[TranslationResult]]:
        """校验 payload 结构，分离有效和无效项。"""
        valid_items: list[ContentItem] = []
        failed_results: list[TranslationResult] = []
        for item in items:
            text_value = item.source_payload.get(self.PAYLOAD_TEXT_KEY)
            if not isinstance(text_value, str) or not text_value.strip():
                error_msg = (
                    f"源载荷 (source_payload) 中的 '{self.PAYLOAD_TEXT_KEY}' 字段缺失、"
                    f"非字符串或为空。"
                )
                logger.warning(
                    error_msg, business_id=item.business_id, payload=item.source_payload
                )
                engine_error = EngineError(error_message=error_msg, is_retryable=False)
                result = self._build_translation_result(
                    item, target_lang, p_context, engine_output=engine_error
                )
                failed_results.append(result)
            else:
                valid_items.append(item)
        return valid_items, failed_results

    async def _separate_cached_items(
        self,
        batch: list[ContentItem],
        target_lang: str,
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """从批处理中分离出已缓存和未缓存的项。"""
        cached_results: list[TranslationResult] = []
        uncached_items: list[ContentItem] = []
        for item in batch:
            request = TranslationRequest(
                source_payload=item.source_payload,
                source_lang=item.source_lang or p_context.config.source_lang,
                target_lang=target_lang,
                context_hash=get_context_hash(item.context),
                engine_name=active_engine.name,
                engine_version=active_engine.VERSION,
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
        engine_context: BaseContextModel | None,
    ) -> list[Union[EngineSuccess, EngineError]]:
        """调用活动引擎翻译一批未缓存的项。"""

        def get_sort_key(item: ContentItem) -> str:
            # [核心修复] 当源语言为 None 时返回空字符串，确保所有键都是可比较的字符串类型，
            # 从而避免 sorted() 在处理混合类型（str 和 None）时抛出 TypeError。
            return item.source_lang or p_context.config.source_lang or ""

        sorted_items = sorted(items, key=get_sort_key)
        grouped_by_lang = groupby(sorted_items, key=get_sort_key)

        tasks = []
        item_groups_for_tasks: list[list[ContentItem]] = []

        for source_lang_key, item_group_iter in grouped_by_lang:
            item_list = list(item_group_iter)
            item_groups_for_tasks.append(item_list)
            texts_to_translate = [
                item.source_payload[self.PAYLOAD_TEXT_KEY] for item in item_list
            ]
            task = active_engine.atranslate_batch(
                texts=texts_to_translate,
                target_lang=target_lang,
                source_lang=source_lang_key or None,
                context=engine_context,
            )
            tasks.append(task)

        group_results_list = await asyncio.gather(*tasks, return_exceptions=True)
        result_map: dict[str, Union[EngineSuccess, EngineError]] = {}

        for i, group_results in enumerate(group_results_list):
            current_item_group = item_groups_for_tasks[i]
            if isinstance(group_results, BaseException):
                logger.error("一个翻译组的任务执行失败", exc_info=group_results)
                error_msg = f"引擎执行失败: {group_results.__class__.__name__}"
                error_output = EngineError(error_message=error_msg, is_retryable=True)
                for item in current_item_group:
                    result_map[item.translation_id] = error_output
            elif len(group_results) != len(current_item_group):
                error_msg = f"引擎为分组返回的结果数量不匹配({len(group_results)} vs {len(current_item_group)})"
                error_output = EngineError(error_message=error_msg, is_retryable=False)
                for item in current_item_group:
                    result_map[item.translation_id] = error_output
            else:
                for item, result in zip(current_item_group, group_results, strict=True):
                    result_map[item.translation_id] = result

        final_outputs = [result_map[item.translation_id] for item in items]
        return final_outputs

    async def _cache_new_results(
        self,
        results: list[TranslationResult],
        p_context: ProcessingContext,
        active_engine: BaseTranslationEngine[Any],
        item_map: dict[str, ContentItem],
    ) -> None:
        """将新获得的成功翻译结果存入缓存。"""
        tasks_with_ids: list[tuple[asyncio.Task[None], str]] = []
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
                    engine_name=active_engine.name,
                    engine_version=active_engine.VERSION,
                )
                if self.PAYLOAD_TEXT_KEY in res.translated_payload:
                    translated_text = res.translated_payload[self.PAYLOAD_TEXT_KEY]
                    task = asyncio.create_task(
                        p_context.cache.cache_translation_result(
                            request, translated_text
                        )
                    )
                    tasks_with_ids.append((task, res.translation_id))
        if tasks_with_ids:
            tasks = [t for t, _ in tasks_with_ids]
            cache_results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(cache_results):
                if isinstance(result, Exception):
                    translation_id = tasks_with_ids[i][1]
                    logger.warning(
                        "写入翻译缓存时发生错误",
                        error=result,
                        translation_id=translation_id,
                        exc_info=False,
                    )

    def _build_translation_result(
        self,
        item: ContentItem,
        target_lang: str,
        p_context: ProcessingContext,
        *,
        engine_output: Union[EngineSuccess, EngineError] | None = None,
        cached_text: str | None = None,
        error_override: EngineError | None = None,
    ) -> TranslationResult:
        """根据不同的输入源构建一个标准的 `TranslationResult` 对象。"""
        active_engine_name = p_context.config.active_engine.value
        context_hash = get_context_hash(item.context)
        final_error = error_override or (
            engine_output if isinstance(engine_output, EngineError) else None
        )
        if final_error:
            return TranslationResult(
                translation_id=item.translation_id,
                business_id=item.business_id,
                original_payload=item.source_payload,
                translated_payload=None,
                target_lang=target_lang,
                status=TranslationStatus.FAILED,
                engine=active_engine_name,
                error=final_error.error_message,
                from_cache=False,
                context_hash=context_hash,
            )
        translated_text: str | None = None
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
            business_id=item.business_id,
            original_payload=item.source_payload,
            translated_payload=translated_payload,
            target_lang=target_lang,
            status=TranslationStatus.TRANSLATED,
            engine=engine,
            from_cache=from_cache,
            error=None,
            context_hash=context_hash,
        )
