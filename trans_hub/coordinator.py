# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。

它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from itertools import groupby
from typing import Any, Optional, Union, cast

import structlog

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import BaseContextModel, BaseTranslationEngine
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import (
    ContentItem,
    EngineError,
    EngineSuccess,
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash, validate_lang_codes

logger = structlog.get_logger(__name__)


class Coordinator:
    """
    异步主协调器。

    负责编排翻译工作流，全面支持异步引擎、异步持久化和异步任务处理。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.config = config
        self.handler = persistence_handler
        self.cache = TranslationCache(self.config.cache_config)
        self.rate_limiter = rate_limiter
        self.active_engine_name = config.active_engine
        self.initialized = False

        logger.info(
            "协调器初始化开始...", available_engines=list(ENGINE_REGISTRY.keys())
        )

        if self.active_engine_name not in ENGINE_REGISTRY:
            raise ValueError(f"指定的活动引擎 '{self.active_engine_name}' 不可用。")

        self.active_engine: BaseTranslationEngine[Any] = self._create_engine_instance(
            self.active_engine_name
        )

        if self.active_engine.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ValueError(
                f"活动引擎 '{self.active_engine_name}' 需要提供源语言，但全局配置 'source_lang' 未设置。"
            )

        logger.info(
            "协调器初始化完成。",
            active_engine=self.active_engine_name,
            rate_limiter_enabled=bool(self.rate_limiter),
        )

    def _create_engine_instance(self, engine_name: str) -> BaseTranslationEngine[Any]:
        """根据名称创建并返回一个引擎实例。"""
        engine_class = ENGINE_REGISTRY[engine_name]

        # 直接从 config 对象中获取已经由验证器创建好的配置实例
        engine_config_instance = getattr(self.config.engine_configs, engine_name, None)
        if not engine_config_instance:
            # 此处理论上不应被触发，但作为保障
            raise ValueError(f"在配置中未找到引擎 '{engine_name}' 的配置实例。")

        # 直接将配置实例传递给引擎的构造函数
        return engine_class(config=engine_config_instance)

    def switch_engine(self, engine_name: str) -> None:
        if engine_name == self.active_engine_name:
            logger.debug(f"引擎 '{engine_name}' 已是活动引擎，无需切换。")
            return

        logger.info(
            "正在切换活动引擎...",
            current_engine=self.active_engine_name,
            new_engine=engine_name,
        )
        if engine_name not in ENGINE_REGISTRY:
            raise ValueError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        self.active_engine = self._create_engine_instance(engine_name)
        self.active_engine_name = engine_name
        self.config.active_engine = engine_name

        logger.info(f"成功切换活动引擎至: '{self.active_engine_name}'。")

    async def initialize(self) -> None:
        if self.initialized:
            return
        logger.info("正在连接持久化存储...")
        await self.handler.connect()
        self.initialized = True
        logger.info("持久化存储连接成功。")

    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
        max_retries: Optional[int] = None,
        initial_backoff: Optional[float] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        validate_lang_codes([target_lang])

        batch_policy = getattr(
            self.active_engine.config, "max_batch_size", self.config.batch_size
        )
        final_batch_size = min(batch_size or self.config.batch_size, batch_policy)
        final_max_retries = max_retries or self.config.retry_policy.max_attempts
        final_initial_backoff = (
            initial_backoff or self.config.retry_policy.initial_backoff
        )

        logger.info(
            "开始处理待翻译任务。",
            target_lang=target_lang,
            batch_size=final_batch_size,
            max_retries=final_max_retries,
        )

        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED],
            batch_size=final_batch_size,
            limit=limit,
        )

        async for batch in content_batches:
            if not batch:
                continue

            # 按 context_hash 对批次进行分组，以确保上下文一致性
            batch.sort(key=lambda item: item.context_hash)
            for context_hash, items_group_iter in groupby(
                batch, key=lambda item: item.context_hash
            ):
                items_group = list(items_group_iter)
                logger.debug(
                    "正在处理一个上下文一致的小组",
                    context_hash=context_hash,
                    item_count=len(items_group),
                )

                # 对每个上下文一致的小组调用重试逻辑
                batch_results = await self._process_batch_with_retry_logic(
                    items_group, target_lang, final_max_retries, final_initial_backoff
                )

                await self.handler.save_translations(batch_results)
                for result in batch_results:
                    if (
                        result.status == TranslationStatus.TRANSLATED
                        and result.business_id
                    ):
                        await self.handler.touch_source(result.business_id)
                    yield result

    async def _process_batch_with_retry_logic(
        self,
        batch: list[ContentItem],
        target_lang: str,
        max_retries: int,
        initial_backoff: float,
    ) -> list[TranslationResult]:
        business_id_map = await self._get_business_id_map(batch)
        validated_context = self._validate_and_get_context(batch)

        if isinstance(validated_context, EngineError):
            logger.warning(
                "批次上下文验证失败，整个批次将标记为失败。",
                error=validated_context.error_message,
            )
            return [
                self._build_translation_result(
                    item, target_lang, business_id_map, error_override=validated_context
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
                items_to_process, target_lang, business_id_map, validated_context
            )
            final_results.extend(processed_results)

            if not retryable_items:
                logger.debug(f"上下文小组处理完成（尝试 {attempt + 1}）。")
                return final_results

            if attempt >= max_retries:
                logger.error(
                    f"上下文小组达到最大重试次数 ({max_retries + 1})。",
                    retry_item_count=len(retryable_items),
                    context_hash=batch[0].context_hash if batch else "N/A",
                )
                error = EngineError(
                    error_message="达到最大重试次数", is_retryable=False
                )
                failed_results = [
                    self._build_translation_result(
                        item, target_lang, business_id_map, error_override=error
                    )
                    for item in retryable_items
                ]
                final_results.extend(failed_results)
                return final_results

            items_to_process = retryable_items
            backoff_time = initial_backoff * (2**attempt)
            logger.warning(
                f"小组中包含可重试的错误，将在 {backoff_time:.2f} 秒后重试。",
                retry_count=len(items_to_process),
            )
            await asyncio.sleep(backoff_time)
        return final_results

    async def _process_single_translation_attempt(
        self,
        batch: list[ContentItem],
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
        context: Optional[BaseContextModel],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        cached_results, uncached_items = await self._separate_cached_items(
            batch, target_lang, business_id_map
        )

        if not uncached_items:
            return cached_results, []

        engine_outputs = await self._translate_uncached_items(
            uncached_items, target_lang, context
        )

        processed_results: list[TranslationResult] = list(cached_results)
        retryable_items: list[ContentItem] = []

        for item, output in zip(uncached_items, engine_outputs):
            if isinstance(output, EngineError) and output.is_retryable:
                retryable_items.append(item)
            else:
                result = self._build_translation_result(
                    item, target_lang, business_id_map, engine_output=output
                )
                processed_results.append(result)

        await self._cache_new_results(processed_results, target_lang)
        return processed_results, retryable_items

    async def _get_business_id_map(
        self, batch: list[ContentItem]
    ) -> dict[tuple[int, str], Optional[str]]:
        if not batch:
            return {}
        tasks = [
            self.handler.get_business_id_for_content(item.content_id, item.context_hash)
            for item in batch
        ]
        retrieved_ids = await asyncio.gather(*tasks)
        return {
            (item.content_id, item.context_hash): biz_id
            for item, biz_id in zip(batch, retrieved_ids)
        }

    async def _separate_cached_items(
        self,
        batch: list[ContentItem],
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        cached_results: list[TranslationResult] = []
        uncached_items: list[ContentItem] = []
        for item in batch:
            request = TranslationRequest(
                source_text=item.value,
                source_lang=self.config.source_lang,
                target_lang=target_lang,
                context_hash=item.context_hash,
            )
            cached_text = await self.cache.get_cached_result(request)
            if cached_text:
                result = self._build_translation_result(
                    item, target_lang, business_id_map, cached_text=cached_text
                )
                cached_results.append(result)
            else:
                uncached_items.append(item)
        return cached_results, uncached_items

    async def _translate_uncached_items(
        self,
        items: list[ContentItem],
        target_lang: str,
        context: Optional[BaseContextModel],
    ) -> list[Union[EngineSuccess, EngineError]]:
        if self.rate_limiter:
            await self.rate_limiter.acquire(len(items))
        try:
            logger.debug(
                f"调用异步引擎 '{self.active_engine_name}' 翻译 {len(items)} 个项目。"
            )
            return await self.active_engine.atranslate_batch(
                texts=[item.value for item in items],
                target_lang=target_lang,
                source_lang=self.config.source_lang,
                context=context,
            )
        except Exception as e:
            logger.error(
                "引擎调用失败，将所有项目标记为可重试错误。",
                engine=self.active_engine_name,
                error=str(e),
                exc_info=True,
            )
            return [EngineError(error_message=str(e), is_retryable=True)] * len(items)

    async def _cache_new_results(
        self, results: list[TranslationResult], target_lang: str
    ) -> None:
        tasks = [
            self.cache.cache_translation_result(
                TranslationRequest(
                    source_text=res.original_content,
                    source_lang=self.config.source_lang,
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

    def _validate_and_get_context(
        self, batch: list[ContentItem]
    ) -> Union[BaseContextModel, EngineError, None]:
        if not batch or not self.active_engine.CONTEXT_MODEL or not batch[0].context:
            return None
        try:
            validated_model = self.active_engine.CONTEXT_MODEL.model_validate(
                batch[0].context
            )
            return cast(BaseContextModel, validated_model)
        except Exception as e:
            error_msg = f"上下文验证失败: {e}"
            logger.error(error_msg, context=batch[0].context, exc_info=True)
            return EngineError(error_message=error_msg, is_retryable=False)

    def _build_translation_result(
        self,
        item: ContentItem,
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
        *,
        engine_output: Optional[Union[EngineSuccess, EngineError]] = None,
        cached_text: Optional[str] = None,
        error_override: Optional[EngineError] = None,
    ) -> TranslationResult:
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
                engine=self.active_engine_name,
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
                context_hash=item.context_hash,
                engine=f"{self.active_engine_name} (cached)",
                business_id=biz_id,
            )

        if isinstance(engine_output, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_output.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=engine_output.from_cache,
                context_hash=item.context_hash,
                business_id=biz_id,
            )
        raise TypeError("无法为项目构建 TranslationResult：输入参数无效。")

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        validate_lang_codes(target_langs)
        context_hash = get_context_hash(context)
        context_json = json.dumps(context) if context else None

        await self.handler.ensure_pending_translations(
            text_content=text_content,
            target_langs=target_langs,
            business_id=business_id,
            context_hash=context_hash,
            context_json=context_json,
            source_lang=(source_lang or self.config.source_lang),
            engine_version=self.active_engine.VERSION,
        )
        logger.info(
            "翻译任务已成功入队。", business_id=business_id, num_langs=len(target_langs)
        )

    async def run_garbage_collection(
        self, expiration_days: Optional[int] = None, dry_run: bool = False
    ) -> dict[str, int]:
        days = expiration_days or self.config.gc_retention_days
        logger.info("开始执行垃圾回收。", expiration_days=days, dry_run=dry_run)
        deleted_counts = await self.handler.garbage_collect(
            retention_days=days, dry_run=dry_run
        )
        logger.info("垃圾回收执行完毕。", deleted_counts=deleted_counts)
        return deleted_counts

    async def close(self) -> None:
        if self.initialized:
            logger.info("正在关闭协调器...")
            await self.handler.close()
            self.initialized = False
            logger.info("协调器已成功关闭。")
