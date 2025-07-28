# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。

重构后，它负责高层工作流的编排：动态加载配置、初始化各组件、
从持久化层获取任务、将任务批次委托给处理策略，并将结果存回持久化层。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from itertools import groupby
from typing import Any, Optional

import structlog

from trans_hub.cache import TranslationCache
from trans_hub.config import EngineName, TransHubConfig
from trans_hub.context import ProcessingContext
from trans_hub.engine_registry import ENGINE_REGISTRY, discover_engines
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY
from trans_hub.exceptions import ConfigurationError, EngineNotFoundError
from trans_hub.interfaces import PersistenceHandler
from trans_hub.policies import DefaultProcessingPolicy, ProcessingPolicy
from trans_hub.rate_limiter import RateLimiter
from trans_hub.types import (
    TranslationRequest,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash, validate_lang_codes

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
        """初始化协调器实例，并动态完成引擎配置的加载和验证。"""
        discover_engines()

        self.config = config
        self.handler = persistence_handler
        self.cache = TranslationCache(self.config.cache_config)
        self.rate_limiter = rate_limiter
        self.initialized = False
        self._engine_instances: dict[str, BaseTranslationEngine] = {}

        self._request_semaphore: Optional[asyncio.Semaphore] = None
        if max_concurrent_requests and max_concurrent_requests > 0:
            self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
            logger.info("请求节流功能已启用", max_concurrent=max_concurrent_requests)

        logger.info(
            "协调器初始化开始...", available_engines=list(ENGINE_REGISTRY.keys())
        )

        for engine_name_str, config_class in ENGINE_CONFIG_REGISTRY.items():
            if not hasattr(self.config.engine_configs, engine_name_str):
                logger.debug("为引擎填充默认配置", engine_name=engine_name_str)
                instance = config_class()
                setattr(self.config.engine_configs, engine_name_str, instance)

        if self.config.active_engine.value not in ENGINE_REGISTRY:
            raise EngineNotFoundError(
                f"指定的活动引擎 '{self.config.active_engine.value}' 不可用。 "
                f"可用引擎: {list(ENGINE_REGISTRY.keys())}"
            )

        active_engine_instance = self._get_or_create_engine_instance(
            self.config.active_engine.value
        )
        if active_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ConfigurationError(
                f"活动引擎 '{self.config.active_engine.value}' 需要提供源语言 (TH_SOURCE_LANG)。"
            )

        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

        logger.info("协调器初始化完成。", active_engine=self.config.active_engine.value)

    @property
    def active_engine(self) -> BaseTranslationEngine:
        """动态获取当前的活动翻译引擎实例。"""
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(self, engine_name: str) -> BaseTranslationEngine:
        """从缓存获取或创建并缓存一个引擎实例。"""
        if engine_name not in self._engine_instances:
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(
                    f"引擎 '{engine_name}' 未在引擎注册表中找到。"
                )

            engine_config_instance = getattr(
                self.config.engine_configs, engine_name, None
            )
            if not engine_config_instance:
                raise ConfigurationError(
                    f"未能为引擎 '{engine_name}' 创建或找到配置实例。"
                )

            logger.debug("创建新的引擎实例", engine_name=engine_name)
            self._engine_instances[engine_name] = engine_class(
                config=engine_config_instance
            )

        return self._engine_instances[engine_name]

    def switch_engine(self, engine_name: str) -> None:
        """在运行时切换当前的活动翻译引擎。"""
        if engine_name == self.config.active_engine.value:
            return

        logger.info("正在切换活动引擎...", new_engine=engine_name)
        if engine_name not in ENGINE_REGISTRY:
            raise EngineNotFoundError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        self._get_or_create_engine_instance(engine_name)

        self.config.active_engine = EngineName(engine_name)

        logger.info(f"成功切换活动引擎至: '{self.config.active_engine.value}'。")

    async def initialize(self) -> None:
        """
        初始化协调器，包括连接持久化存储和初始化所有引擎。
        这是一个幂等操作。
        """
        if self.initialized:
            return

        logger.info("正在连接持久化存储...")
        await self.handler.connect()
        await self.handler.reset_stale_tasks()

        logger.info("正在初始化所有翻译引擎...")
        # --- 核心修正：恢复正确的 asyncio.gather 写法 ---
        # 创建所有引擎实例（如果尚未创建），并收集它们的 initialize 协程
        init_tasks = [
            self._get_or_create_engine_instance(name).initialize()
            for name in ENGINE_REGISTRY.keys()
        ]
        # 并发执行所有初始化任务
        await asyncio.gather(*init_tasks)

        self.initialized = True
        logger.info("持久化存储和所有引擎已初始化。")

    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """处理指定语言的待翻译任务，并以异步生成器方式返回翻译结果。"""
        validate_lang_codes([target_lang])

        active_engine = self.active_engine
        engine_batch_policy = getattr(
            active_engine.config, "max_batch_size", self.config.batch_size
        )
        final_batch_size = min(
            batch_size or self.config.batch_size, engine_batch_policy
        )

        logger.info(
            "开始处理待翻译任务。", target_lang=target_lang, batch_size=final_batch_size
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

            batch.sort(key=lambda item: item.context_hash)
            for context_hash, items_group_iter in groupby(
                batch, key=lambda item: item.context_hash
            ):
                items_group = list(items_group_iter)
                logger.debug(
                    "正在处理上下文一致的小组",
                    context_hash=context_hash,
                    item_count=len(items_group),
                )

                batch_results = await self.processing_policy.process_batch(
                    items_group, target_lang, self.processing_context, active_engine
                )

                await self.handler.save_translations(batch_results)
                for result in batch_results:
                    if (
                        result.status == TranslationStatus.TRANSLATED
                        and result.business_id
                    ):
                        await self.handler.touch_source(result.business_id)
                    yield result

    async def _request_internal(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str],
        context: Optional[dict[str, Any]],
        source_lang: Optional[str],
        force_retranslate: bool,
    ) -> None:
        """[私有] `request` 方法的内部实现，用于被信号量包裹。"""
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
            force_retranslate=force_retranslate,
        )
        logger.info(
            "翻译任务已成功入队。", business_id=business_id, num_langs=len(target_langs)
        )

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
        """提交一个新的翻译请求，将其加入待处理队列。"""
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

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """立即获取一个已完成的翻译结果。"""
        validate_lang_codes([target_lang])
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
        """执行垃圾回收，清理超过指定天数未被访问的源数据及其关联的孤立内容。"""
        days = expiration_days or self.config.gc_retention_days
        logger.info("开始执行垃圾回收。", expiration_days=days, dry_run=dry_run)
        deleted_counts = await self.handler.garbage_collect(
            retention_days=days, dry_run=dry_run
        )
        logger.info("垃圾回收执行完毕。", deleted_counts=deleted_counts)
        return deleted_counts

    async def close(self) -> None:
        """安全地关闭协调器及其管理的所有资源（数据库连接和引擎）。"""
        if self.initialized:
            logger.info("正在关闭协调器...")

            logger.info("正在关闭所有翻译引擎...")
            close_tasks = [
                instance.close() for instance in self._engine_instances.values()
            ]
            await asyncio.gather(*close_tasks)

            await self.handler.close()
            self.initialized = False
            logger.info("协调器及所有资源已成功关闭。")
