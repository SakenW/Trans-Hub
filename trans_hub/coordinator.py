# trans_hub/coordinator.py (修正版)
"""本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。

它采用动态引擎发现机制，并负责编排所有核心工作流，包括任务处理、重试、
速率限制、请求处理和垃圾回收等。
v2.4.1: 修正因重构引入的导入路径错误。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, Optional, Union

import structlog

from trans_hub.cache import TranslationCache
from trans_hub.config import TransHubConfig
from trans_hub.engine_registry import ENGINE_REGISTRY

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼【修改点 1：拆分导入】▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
from trans_hub.engines.base import (
    BaseContextModel,
    BaseTranslationEngine,
    EngineBatchItemResult,
)
from trans_hub.interfaces import PersistenceHandler
from trans_hub.rate_limiter import RateLimiter

# ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼【修改点 2：从正确的位置导入】▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
from trans_hub.types import (
    ContentItem,
    EngineError,  # 从 types.py 导入
    EngineSuccess,  # 从 types.py 导入
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)

# ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
from trans_hub.utils import get_context_hash, validate_lang_codes

# 使用 structlog 获取结构化的日志记录器
logger = structlog.get_logger(__name__)


class Coordinator:
    """异步主协调器。

    负责编排翻译工作流，全面支持异步引擎、异步持久化和异步任务处理。
    """

    # ... 文件余下内容保持不变，无需修改 ...
    # 我在这里省略了后面的代码，您只需替换文件开头的导入部分即可。
    # 完整的代码在之前的回答中，这里只展示变化的部分。
    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        """初始化协调器实例。

        Args:
        ----
            config (TransHubConfig): Trans-Hub 的全局配置对象。
            persistence_handler (PersistenceHandler): 持久化处理器实例。
            rate_limiter (Optional[RateLimiter]): 可选的速率限制器实例。

        """
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
        """根据名称创建并返回一个引擎实例。

        Args:
        ----
            engine_name (str): 目标引擎的名称。

        Returns:
        -------
            BaseTranslationEngine[Any]: 初始化后的引擎实例。

        Raises:
        ------
            ValueError: 如果引擎配置不存在。

        """
        engine_class = ENGINE_REGISTRY[engine_name]
        engine_config_data = getattr(self.config.engine_configs, engine_name, None)
        if not engine_config_data:
            raise ValueError(f"在配置中未找到引擎 '{engine_name}' 的配置。")

        engine_config_instance = engine_class.CONFIG_MODEL(
            **engine_config_data.model_dump()
        )
        return engine_class(config=engine_config_instance)

    def switch_engine(self, engine_name: str) -> None:
        """动态切换当前活动的翻译引擎实例。

        Args:
        ----
            engine_name (str): 要切换到的新引擎的名称。

        Raises:
        ------
            ValueError: 如果目标引擎不可用。

        """
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

        logger.info(f"✅ 成功切换活动引擎至: '{self.active_engine_name}'。")

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
        """处理指定语言的待翻译任务，内置重试和速率限制逻辑。

        Args:
        ----
            target_lang (str): 目标翻译语言。
            batch_size (Optional[int]): 每个批次的大小，默认为全局配置。
            limit (Optional[int]): 要处理的最大项目数。
            max_retries (Optional[int]): 最大重试次数，默认为全局配置。
            initial_backoff (Optional[float]): 初始退避时间（秒），默认为全局配置。

        Yields:
        ------
            TranslationResult: 每个处理完成的翻译结果。

        """
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

            logger.debug(f"正在处理一个包含 {len(batch)} 个内容的批次。")
            batch_results = await self._process_batch_with_retry_logic(
                batch, target_lang, final_max_retries, final_initial_backoff
            )

            await self.handler.save_translations(batch_results)
            for result in batch_results:
                if result.status == TranslationStatus.TRANSLATED and result.business_id:
                    await self.handler.touch_source(result.business_id)
                yield result

    async def _process_batch_with_retry_logic(
        self,
        batch: list[ContentItem],
        target_lang: str,
        max_retries: int,
        initial_backoff: float,
    ) -> list[TranslationResult]:
        """对单个批次进行处理，包含完整的重试、缓存和 business_id 处理逻辑。

        这是核心重试循环的封装。

        Args:
        ----
            batch (list[ContentItem]): 待处理的内容项批次。
            target_lang (str): 目标语言。
            max_retries (int): 最大重试次数。
            initial_backoff (float): 初始退避时间。

        Returns:
        -------
            list[TranslationResult]: 批次处理后的最终结果列表。

        """
        # 预先获取 business_id，避免在循环中重复查询
        business_id_map = await self._get_business_id_map(batch)

        # 预先验证上下文，如果失败则直接标记整个批次失败
        validated_context = self._validate_and_get_context(batch)
        if isinstance(validated_context, EngineError):
            logger.warning(
                "批次上下文验证失败，整个批次将标记为失败。",
                error=validated_context.error_message,
            )
            return [
                self._create_translation_result_from_error(
                    item, validated_context, target_lang, business_id_map
                )
                for item in batch
            ]

        items_to_process = list(batch)
        final_results: list[TranslationResult] = []

        for attempt in range(max_retries + 1):
            try:
                (
                    processed_results,
                    retryable_items,
                ) = await self._process_single_translation_attempt(
                    items_to_process, target_lang, business_id_map, validated_context
                )

                final_results.extend(processed_results)

                # 如果没有需要重试的项目，直接结束循环
                if not retryable_items:
                    logger.info(f"批次处理完成（尝试 {attempt + 1}）。")
                    return final_results

                # 如果达到最大重试次数，结束循环
                if attempt >= max_retries:
                    logger.error(
                        f"批次处理达到最大重试次数 ({max_retries + 1})，将保留失败状态。",
                        retry_item_count=len(retryable_items),
                    )
                    # 将最后一次失败的重试项也加入最终结果
                    failed_results = [
                        self._create_translation_result_from_error(
                            item,
                            EngineError(
                                error_message="达到最大重试次数", is_retryable=True
                            ),  # 标记为最后一次失败
                            target_lang,
                            business_id_map,
                        )
                        for item in retryable_items
                    ]
                    final_results.extend(failed_results)
                    return final_results

                # 准备下一次重试
                items_to_process = retryable_items
                backoff_time = initial_backoff * (2**attempt)
                logger.warning(
                    f"批次中包含可重试的错误，将在 {backoff_time:.2f} 秒后重试。",
                    retry_count=len(items_to_process),
                )
                await asyncio.sleep(backoff_time)

            except Exception as e:
                logger.error("处理批次时发生意外异常。", error=str(e), exc_info=True)
                error = EngineError(error_message=f"意外错误: {e}", is_retryable=False)
                # 如果发生意外，将所有待处理的项标记为失败
                error_results = [
                    self._create_translation_result_from_error(
                        item, error, target_lang, business_id_map
                    )
                    for item in items_to_process
                ]
                final_results.extend(error_results)
                return final_results  # 出现意外情况，立即返回

        return final_results  # 正常情况下不应执行到这里，但作为保障

    async def _process_single_translation_attempt(
        self,
        batch: list[ContentItem],
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
        context: Optional[BaseContextModel],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """执行单次翻译尝试，包括缓存检查、API调用和结果分类。

        Args:
        ----
            batch (list[ContentItem]): 当前尝试要处理的项目。
            target_lang (str): 目标语言。
            business_id_map (dict): 预先获取的 business_id 映射。
            context (Optional[BaseContextModel]): 已验证的上下文模型。

        Returns:
        -------
            tuple[list[TranslationResult], list[ContentItem]]:
                - 第一个元素是本次尝试中成功或不可重试的失败结果。
                - 第二个元素是本次尝试中失败且可重试的原始 ContentItem 列表。

        """
        # 1. 从缓存分离
        cached_results, uncached_items = await self._separate_cached_items(
            batch, target_lang, business_id_map
        )

        if not uncached_items:
            logger.debug("批次中的所有项目都在缓存中找到。")
            return cached_results, []

        # 2. 翻译未缓存的项目
        engine_outputs = await self._translate_uncached_items(
            uncached_items, target_lang, context
        )

        # 3. 处理引擎输出并分类
        processed_results: list[TranslationResult] = list(cached_results)
        retryable_items: list[ContentItem] = []

        for item, output in zip(uncached_items, engine_outputs):
            if isinstance(output, EngineSuccess):
                result = self._convert_to_translation_result(
                    item, output, target_lang, business_id_map
                )
                processed_results.append(result)
            elif isinstance(output, EngineError):
                if output.is_retryable:
                    retryable_items.append(item)
                else:
                    result = self._create_translation_result_from_error(
                        item, output, target_lang, business_id_map
                    )
                    processed_results.append(result)
            else:
                # 处理未知的引擎输出类型，视为不可重试错误
                error = EngineError(
                    f"未知的引擎结果类型: {type(output)}", is_retryable=False
                )
                result = self._create_translation_result_from_error(
                    item, error, target_lang, business_id_map
                )
                processed_results.append(result)

        # 4. 缓存新结果
        await self._cache_new_results(processed_results, target_lang)

        return processed_results, retryable_items

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

    async def _separate_cached_items(
        self,
        batch: list[ContentItem],
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
    ) -> tuple[list[TranslationResult], list[ContentItem]]:
        """从批次中分离出已缓存和未缓存的项目。"""
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
                    engine=f"{self.active_engine_name} (cached)",
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
        """调用翻译引擎处理未缓存的项目。"""
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
        """将新的成功翻译结果存入缓存。"""
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
        """验证批次的上下文是否一致且有效。"""
        if not batch or not self.active_engine.CONTEXT_MODEL or not batch[0].context:
            return None
        try:
            # 假设批次内所有项目的上下文都相同，取第一个进行验证
            return self.active_engine.CONTEXT_MODEL.model_validate(batch[0].context)
        except Exception as e:
            error_msg = f"上下文验证失败: {e}"
            logger.error(error_msg, context=batch[0].context, exc_info=True)
            return EngineError(error_message=error_msg, is_retryable=False)

    def _convert_to_translation_result(
        self,
        item: ContentItem,
        engine_result: EngineSuccess,
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
    ) -> TranslationResult:
        """将引擎的成功输出转换为标准的 TranslationResult。"""
        biz_id = business_id_map.get((item.content_id, item.context_hash))
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

    def _create_translation_result_from_error(
        self,
        item: ContentItem,
        error: EngineError,
        target_lang: str,
        business_id_map: dict[tuple[int, str], Optional[str]],
    ) -> TranslationResult:
        """根据引擎错误创建失败状态的 TranslationResult。"""
        biz_id = business_id_map.get((item.content_id, item.context_hash))
        return TranslationResult(
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

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
    ) -> None:
        """统一的翻译请求入口，完全封装了数据库交互。

        Args:
        ----
            target_langs (list[str]): 目标语言代码列表。
            text_content (str): 需要翻译的文本内容。
            business_id (Optional[str]): 关联的业务ID。
            context (Optional[dict[str, Any]]): 翻译上下文信息。
            source_lang (Optional[str]): 源语言，如果提供则覆盖全局配置。

        """
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
        """异步运行垃圾回收进程，清理过期的翻译记录。

        Args:
        ----
            expiration_days (Optional[int]): 数据保留天数，默认为全局配置。
            dry_run (bool): 如果为 True，则只报告将要删除的数量而不实际删除。

        Returns:
        -------
            dict[str, int]: 一个字典，报告每个表中删除的行数。

        """
        days = expiration_days or self.config.gc_retention_days
        logger.info("开始执行垃圾回收。", expiration_days=days, dry_run=dry_run)
        deleted_counts = await self.handler.garbage_collect(
            retention_days=days, dry_run=dry_run
        )
        logger.info("垃圾回收执行完毕。", deleted_counts=deleted_counts)
        return deleted_counts

    async def close(self) -> None:
        """优雅地关闭协调器及其持有的资源，如数据库连接。"""
        if self.initialized:
            logger.info("正在关闭协调器...")
            await self.handler.close()
            self.initialized = False
            logger.info("协调器已成功关闭。")
