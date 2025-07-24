# trans_hub/coordinator.py (终极完美版)
"""本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。

它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
v2.3.0: 提取通用验证逻辑到 utils 模块，完成最终代码审查。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, Optional, Union

import structlog

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import (
    BaseContextModel,
    BaseTranslationEngine,
    EngineBatchItemResult,
)
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
    """异步主协调器。
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
                f"活动引擎 '{self.active_engine_name}' 需要提供源语言, 但全局配置 'source_lang' 未设置。"
            )

        logger.info(
            "协调器初始化完成",
            active_engine=self.active_engine_name,
            rate_limiter_enabled=bool(self.rate_limiter),
        )

    def _create_engine_instance(self, engine_name: str) -> BaseTranslationEngine[Any]:
        """根据名称创建并返回一个引擎实例。"""
        engine_class = ENGINE_REGISTRY[engine_name]
        engine_config_data = getattr(self.config.engine_configs, engine_name, None)
        if not engine_config_data:
            raise ValueError(f"在配置中未找到引擎 '{engine_name}' 的配置。")

        engine_config_instance = engine_class.CONFIG_MODEL(
            **engine_config_data.model_dump()
        )
        return engine_class(config=engine_config_instance)

    def switch_engine(self, engine_name: str) -> None:
        """动态切换当前活动的翻译引擎实例。"""
        if engine_name == self.active_engine_name:
            return

        logger.info(
            f"正在切换活动引擎: 从 '{self.active_engine_name}' -> '{engine_name}'..."
        )
        if engine_name not in ENGINE_REGISTRY:
            raise ValueError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        self.active_engine = self._create_engine_instance(engine_name)
        self.active_engine_name = engine_name
        self.config.active_engine = engine_name

        logger.info(f"✅ 成功切换活动引擎至: '{self.active_engine_name}'")

    async def initialize(self) -> None:
        """异步初始化协调器，主要用于建立数据库连接。"""
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
        """处理指定语言的待翻译任务，内置重试和速率限制逻辑。"""
        validate_lang_codes([target_lang])

        engine_batch_size = getattr(
            self.active_engine, "MAX_BATCH_SIZE", self.config.batch_size
        )
        final_batch_size = min(batch_size or self.config.batch_size, engine_batch_size)
        final_max_retries = max_retries or self.config.retry_policy.max_attempts
        final_initial_backoff = (
            initial_backoff or self.config.retry_policy.initial_backoff
        )

        logger.info(
            "开始处理待翻译任务", target_lang=target_lang, batch_size=final_batch_size
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

            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            batch_results = await self._process_batch_with_retries(
                batch, target_lang, final_max_retries, final_initial_backoff
            )

            await self.handler.save_translations(batch_results)
            for result in batch_results:
                if result.status == TranslationStatus.TRANSLATED and result.business_id:
                    await self.handler.touch_source(result.business_id)
                yield result

    async def _get_business_id_map(
        self, batch: list[ContentItem]
    ) -> dict[tuple[int, str], Optional[str]]:
        """为一个批次并发获取所有的 business_id，避免 N+1 查询。"""
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

    async def _process_batch_with_retries(
        self,
        batch: list[ContentItem],
        target_lang: str,
        max_retries: int,
        initial_backoff: float,
    ) -> list[TranslationResult]:
        """对单个批次进行处理，包含完整的重试、缓存和 business_id 处理逻辑。"""
        validated_context = self._validate_and_get_context(batch)
        if isinstance(validated_context, EngineError):
            logger.warning("批次上下文验证失败，整个批次将标记为失败。")
            return [
                self._create_translation_result_from_error(
                    item, validated_context, target_lang
                )
                for item in batch
            ]

        business_id_map = await self._get_business_id_map(batch)

        for attempt in range(max_retries + 1):
            try:
                cached_results, uncached_items = await self._separate_cached_items(
                    batch, target_lang, business_id_map
                )

                if not uncached_items:
                    logger.debug("批次中的所有项目都从缓存中找到。")
                    return cached_results

                engine_outputs = await self._translate_uncached_items(
                    uncached_items, target_lang, validated_context
                )
                new_results = [
                    self._convert_to_translation_result(
                        item, output, target_lang, business_id_map
                    )
                    for item, output in zip(uncached_items, engine_outputs)
                ]
                final_results = cached_results + new_results
                await self._cache_new_results(new_results, target_lang)

                if not any(self._is_error_retryable(res) for res in final_results):
                    logger.info(
                        f"批次处理成功或遇到不可重试错误 (尝试 {attempt + 1})。"
                    )
                    return final_results

                if attempt >= max_retries:
                    logger.error(
                        f"批次处理达到最大重试次数 ({max_retries + 1})，将保留失败状态。"
                    )
                    return final_results

                backoff_time = initial_backoff * (2**attempt)
                logger.warning(
                    f"批次中包含可重试的错误，将在 {backoff_time:.2f} 秒后重试。"
                )
                await asyncio.sleep(backoff_time)
            except Exception as e:
                logger.error("处理批次时发生意外异常", error=str(e), exc_info=True)
                error = EngineError(error_message=f"意外错误: {e}", is_retryable=False)
                return [
                    self._create_translation_result_from_error(
                        item, error, target_lang, business_id_map
                    )
                    for item in batch
                ]
        return []

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
                biz_id = business_id_map.get((item.content_id, item.context_hash))
                result = TranslationResult(
                    original_content=item.value,
                    translated_content=cached_text,
                    target_lang=target_lang,
                    status=TranslationStatus.TRANSLATED,
                    from_cache=True,
                    context_hash=item.context_hash,
                    engine=self.active_engine_name,
                    business_id=biz_id,
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
    ) -> list[EngineBatchItemResult]:
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
                "引擎调用失败",
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
            return self.active_engine.CONTEXT_MODEL.model_validate(batch[0].context)
        except Exception as e:
            error_msg = f"上下文验证失败: {e}"
            logger.error(error_msg, context=batch[0].context, exc_info=True)
            return EngineError(error_message=error_msg, is_retryable=False)

    def _convert_to_translation_result(
        self,
        item: ContentItem,
        engine_result: EngineBatchItemResult,
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
    ) -> TranslationResult:
        biz_id = business_id_map.get((item.content_id, item.context_hash))
        if isinstance(engine_result, EngineSuccess):
            return TranslationResult(
                original_content=item.value,
                translated_content=engine_result.translated_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=self.active_engine_name,
                from_cache=engine_result.from_cache,
                context_hash=item.context_hash,
                business_id=biz_id,
            )
        elif isinstance(engine_result, EngineError):
            return self._create_translation_result_from_error(
                item, engine_result, target_lang, business_id_map
            )
        raise TypeError(f"未知的引擎结果类型: {type(engine_result)}。")

    def _create_translation_result_from_error(
        self,
        item: ContentItem,
        error: EngineError,
        target_lang: str,
        business_id_map: Optional[dict[tuple[int, str], Optional[str]]] = None,
    ) -> TranslationResult:
        biz_id = (
            business_id_map.get((item.content_id, item.context_hash))
            if business_id_map
            else None
        )
        result = TranslationResult(
            original_content=item.value,
            translated_content=None,
            target_lang=target_lang,
            status=TranslationStatus.FAILED,
            engine=self.active_engine_name,
            error=error.error_message,
            from_cache=False,
            context_hash=item.context_hash,
            business_id=biz_id,
        )
        result._is_retryable = error.is_retryable
        return result

    def _is_error_retryable(self, result: TranslationResult) -> bool:
        return getattr(result, "_is_retryable", False)

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        """统一的翻译请求入口，完全封装了数据库交互。"""
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
            "翻译任务已成功入队", business_id=business_id, num_langs=len(target_langs)
        )

    async def run_garbage_collection(
        self, expiration_days: Optional[int] = None, dry_run: bool = False
    ) -> dict[str, int]:
        """异步运行垃圾回收进程。"""
        days = expiration_days or self.config.gc_retention_days
        logger.info("开始执行垃圾回收", expiration_days=days, dry_run=dry_run)
        return await self.handler.garbage_collect(retention_days=days, dry_run=dry_run)

    async def close(self) -> None:
        """优雅地关闭协调器及其持有的资源。"""
        if self.initialized:
            logger.info("正在关闭协调器...")
            await self.handler.close()
            self.initialized = False
            logger.info("协调器已成功关闭。")
