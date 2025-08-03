# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
v3.1 修订：移除了不属于其核心职责的 `run_migrations` 方法。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from itertools import groupby
from typing import TYPE_CHECKING, Any, Optional

import structlog

from .cache import TranslationCache
from .config import EngineName, TransHubConfig
from .context import ProcessingContext
from .engine_registry import ENGINE_REGISTRY, discover_engines
from .exceptions import ConfigurationError, EngineNotFoundError
from .interfaces import PersistenceHandler
from .policies import DefaultProcessingPolicy, ProcessingPolicy
from .rate_limiter import RateLimiter
from .types import (
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)
from .utils import get_context_hash

if TYPE_CHECKING:
    from .engines.base import BaseTranslationEngine

logger = structlog.get_logger(__name__)


class Coordinator:
    """异步主协调器，是 Trans-Hub 功能的中心枢纽。"""

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
        max_concurrent_requests: Optional[int] = None,
    ) -> None:
        """初始化 Coordinator。

        Args:
            config: Trans-Hub 的主配置对象。
            persistence_handler: 实现了 PersistenceHandler 协议的持久化处理器实例。
            rate_limiter: 可选的速率限制器实例。
            max_concurrent_requests: 可选的最大并发请求数。
        """
        discover_engines()
        self.config = config
        self.handler = persistence_handler
        self.cache = TranslationCache(self.config.cache_config)
        self.rate_limiter = rate_limiter
        self.initialized = False
        self._engine_instances: dict[str, "BaseTranslationEngine[Any]"] = {}
        self._request_semaphore: Optional[asyncio.Semaphore] = None
        if max_concurrent_requests and max_concurrent_requests > 0:
            self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)

        self._shutting_down = False
        self._active_processors = 0
        self._processor_lock = asyncio.Lock()
        self._shutdown_complete_event = asyncio.Event()

        logger.info(
            "协调器已创建，等待初始化。", available_engines=list(ENGINE_REGISTRY.keys())
        )

        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

    @property
    def active_engine(self) -> "BaseTranslationEngine[Any]":
        """获取当前活动的翻译引擎实例。

        Returns:
            当前活动的引擎实例。
        """
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> "BaseTranslationEngine[Any]":
        """根据引擎名称获取或创建引擎实例（惰性加载）。

        Args:
            engine_name: 引擎的名称。

        Returns:
            请求的引擎实例。

        Raises:
            EngineNotFoundError: 如果请求的引擎未注册。
        """
        if engine_name not in self._engine_instances:
            logger.debug("首次请求，正在创建引擎实例...", engine_name=engine_name)
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(
                    f"引擎 '{engine_name}' 未在引擎注册表中找到。"
                )

            engine_config_data = getattr(self.config.engine_configs, engine_name, None)
            engine_config_instance = engine_config_data or engine_class.CONFIG_MODEL()

            self._engine_instances[engine_name] = engine_class(
                config=engine_config_instance
            )
            logger.info("引擎实例创建成功。", engine_name=engine_name)
        return self._engine_instances[engine_name]

    def switch_engine(self, engine_name: str) -> None:
        """切换当前的活动翻译引擎。

        Args:
            engine_name: 新的活动引擎的名称。

        Raises:
            EngineNotFoundError: 如果目标引擎不可用。
            ConfigurationError: 如果目标引擎需要源语言但未配置。
        """
        if engine_name == self.config.active_engine.value:
            return

        if engine_name not in ENGINE_REGISTRY:
            raise EngineNotFoundError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        new_engine_instance = self._get_or_create_engine_instance(engine_name)
        if new_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ConfigurationError(f"切换失败：引擎 '{engine_name}' 需要提供源语言。")

        self.config.active_engine = EngineName(engine_name)
        logger.info("成功切换活动引擎。", new_engine=self.config.active_engine.value)

    async def initialize(self) -> None:
        """初始化协调器，包括连接数据库和初始化活动引擎。"""
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        try:
            active_engine_instance = self.active_engine
            if (
                active_engine_instance.REQUIRES_SOURCE_LANG
                and not self.config.source_lang
            ):
                raise ConfigurationError(
                    f"活动引擎 '{self.config.active_engine.value}' 需要提供源语言。"
                )
        except Exception as e:
            logger.error(
                "初始化活动引擎时失败。",
                engine=self.config.active_engine.value,
                exc_info=True,
            )
            raise e
        await self.handler.connect()
        await self.handler.reset_stale_tasks()
        init_tasks = [
            instance.initialize() for instance in self._engine_instances.values()
        ]
        if init_tasks:
            await asyncio.gather(*init_tasks)
        self.initialized = True
        logger.info("协调器初始化完成。", active_engine=self.config.active_engine.value)

    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """处理指定语言的待处理翻译任务。

        这是一个异步生成器，会持续产出翻译结果直到处理完所有待处理项。

        Args:
            target_lang: 目标语言代码。
            batch_size: 每个批次处理的大小。如果为 None, 则使用全局配置。
            limit: 本次调用最多处理的任务数量。

        Yields:
            TranslationResult 对象。
        """
        if self._shutting_down:
            return

        active_engine = self.active_engine
        engine_batch_policy = getattr(
            active_engine.config, "max_batch_size", self.config.batch_size
        )
        final_batch_size = min(
            batch_size or self.config.batch_size, engine_batch_policy
        )

        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED],
            batch_size=final_batch_size,
            limit=limit,
        )

        async for batch in content_batches:
            if self._shutting_down:
                logger.warning("检测到停机信号，翻译工作进程将不再处理新批次。")
                break

            if not batch:
                continue

            batch.sort(key=lambda item: item.context_id or "")
            for _context_id, items_group_iter in groupby(
                batch, key=lambda item: item.context_id
            ):
                items_group = list(items_group_iter)

                async with self._processor_lock:
                    self._active_processors += 1

                try:
                    batch_results = await self.processing_policy.process_batch(
                        items_group, target_lang, self.processing_context, active_engine
                    )
                    # 在一个事务中处理保存翻译结果和更新作业时间戳
                    async with self.handler._transaction() as cursor:
                        await self.handler.save_translations(batch_results, cursor)
                        business_ids = [
                            result.business_id
                            for result in batch_results
                            if result.status == TranslationStatus.TRANSLATED and result.business_id
                        ]
                        if business_ids:
                            await self.handler.touch_jobs(business_ids, cursor)
                    # 事务完成后产出结果
                    for result in batch_results:
                        yield result
                finally:
                    async with self._processor_lock:
                        self._active_processors -= 1
                        if self._shutting_down and self._active_processors == 0:
                            self._shutdown_complete_event.set()

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
        """提交一个新的翻译请求。

        此方法将请求加入持久化队列，由后台 Worker 异步处理。

        Args:
            target_langs: 目标语言代码列表。
            text_content: 要翻译的原文。
            business_id: 关联的业务ID，可选。
            context: 翻译上下文信息，可选。
            source_lang: 源语言。如果为 None, 则使用全局配置。
            force_retranslate: 是否强制重新翻译，即使已有缓存或成功记录。
        """
        if self._shutting_down:
            logger.warning("系统正在停机，已拒绝新的翻译请求。")
            return
        if self._request_semaphore:
            async with self._request_semaphore:
                await self._request_internal(
                    target_langs,
                    text_content,
                    business_id,
                    context,
                    source_lang,
                    force_retranslate,
                )
        else:
            await self._request_internal(
                target_langs,
                text_content,
                business_id,
                context,
                source_lang,
                force_retranslate,
            )

    async def _request_internal(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str],
        context: Optional[dict[str, Any]],
        source_lang: Optional[str],
        force_retranslate: bool,
    ) -> None:
        """内部请求处理逻辑。"""
        context_hash = get_context_hash(context)
        context_json = json.dumps(context, ensure_ascii=False) if context else None
        await self.handler.ensure_pending_translations(
            text_content=text_content,
            target_langs=target_langs,
            business_id=business_id,
            context_hash=context_hash,
            context_json=context_json,
            source_lang=(source_lang or self.config.source_lang),
            engine_version=self.active_engine.VERSION,
            force_retranslate=force_retranslate,
        )

    async def touch_jobs(self, business_ids: list[str]) -> None:
        """更新一个或多个业务ID关联任务的 `updated_at` 时间戳。

        Args:
            business_ids: 需要“触摸”的业务ID列表。
        """
        if not business_ids:
            return
        await self.handler.touch_jobs(business_ids)

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """直接获取一个翻译结果，会依次查找内存缓存和数据库。

        Args:
            text_content: 原文。
            target_lang: 目标语言。
            context: 上下文信息，可选。

        Returns:
            如果找到，返回 TranslationResult 对象，否则返回 None。
        """
        context_hash = get_context_hash(context)
        request = TranslationRequest(
            source_text=text_content,
            source_lang=self.config.source_lang,
            target_lang=target_lang,
            context_hash=context_hash,
        )
        cached_text = await self.cache.get_cached_result(request)
        if cached_text:
            return TranslationResult(
                translation_id="from-mem-cache",
                original_content=text_content,
                translated_content=cached_text,
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                from_cache=True,
                engine=f"{self.config.active_engine.value} (mem-cached)",
                context_hash=context_hash,
                business_id=None,
            )
        db_result = await self.handler.get_translation(
            text_content, target_lang, context
        )
        if db_result and db_result.translated_content:
            await self.cache.cache_translation_result(
                request, db_result.translated_content
            )
        return db_result

    async def run_garbage_collection(
        self, expiration_days: Optional[int] = None, dry_run: bool = False
    ) -> dict[str, int]:
        """运行垃圾回收，清理旧的、无关联的数据。

        Args:
            expiration_days: 保留天数。如果为 None, 则使用全局配置。
            dry_run: 是否为预演模式，只报告不删除。

        Returns:
            一个包含各类已删除或将被删除项目数量的字典。
        """
        days = expiration_days or self.config.gc_retention_days
        return await self.handler.garbage_collect(retention_days=days, dry_run=dry_run)

    async def close(self) -> None:
        """优雅地关闭协调器和所有相关资源。"""
        if not self.initialized:
            return

        logger.info("开始优雅停机...")
        async with self._processor_lock:
            self._shutting_down = True
            active_count = self._active_processors

        if active_count > 0:
            logger.info(f"等待 {active_count} 个正在进行的批次处理完成...")
            try:
                await asyncio.wait_for(
                    self._shutdown_complete_event.wait(), timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error("优雅停机超时！部分任务可能未完成。")

        logger.info("所有批次处理完成，正在关闭底层资源...")
        close_tasks = [instance.close() for instance in self._engine_instances.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks)
        await asyncio.sleep(0.1)  # 短暂等待以确保异步关闭操作完成
        await self.handler.close()
        self.initialized = False
        logger.info("优雅停机完成。")
