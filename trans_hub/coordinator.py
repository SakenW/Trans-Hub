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
from trans_hub.config import TransHubConfig
from trans_hub.context import ProcessingContext
from trans_hub.engine_registry import ENGINE_REGISTRY, discover_engines
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.engines.meta import ENGINE_CONFIG_REGISTRY
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
    """
    异步主协调器，是 Trans-Hub 功能的中心枢纽。

    它将持久化、缓存、速率限制和翻译引擎等组件组合在一起，通过依赖注入的
    处理策略（ProcessingPolicy）执行核心翻译任务，对外提供统一的接口。
    """

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
        rate_limiter: Optional[RateLimiter] = None,
        max_concurrent_requests: Optional[int] = None,
    ) -> None:
        """
        初始化协调器实例，并动态完成引擎配置的加载和验证。

        参数:
            config: Trans-Hub 的主配置对象。
            persistence_handler: 实现了 PersistenceHandler 协议的持久化处理器实例。
            rate_limiter: 可选的速率限制器实例。
            max_concurrent_requests: 可选的最大并发请求数，用于节流。
        """
        discover_engines()

        self.config = config
        self.handler = persistence_handler
        self.cache = TranslationCache(self.config.cache_config)
        self.rate_limiter = rate_limiter
        self.initialized = False

        self._request_semaphore: Optional[asyncio.Semaphore] = None
        if max_concurrent_requests and max_concurrent_requests > 0:
            self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)
            logger.info("请求节流功能已启用", max_concurrent=max_concurrent_requests)

        logger.info(
            "协调器初始化开始...", available_engines=list(ENGINE_REGISTRY.keys())
        )

        # 确保活动引擎及其配置有效
        if self.config.active_engine not in ENGINE_REGISTRY:
            raise ValueError(f"指定的活动引擎 '{self.config.active_engine}' 不可用。")
        self._ensure_engine_config(self.config.active_engine)
        active_engine_instance = self._create_engine_instance(self.config.active_engine)
        if active_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ValueError(f"活动引擎 '{self.config.active_engine}' 需要提供源语言。")

        # 核心重构：创建处理上下文和策略实例
        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

        logger.info("协调器初始化完成。", active_engine=self.config.active_engine)

    def _ensure_engine_config(self, engine_name: str) -> None:
        """确保指定引擎的配置对象存在于主配置中，如果不存在则使用默认值创建。"""
        if getattr(self.config.engine_configs, engine_name, None) is None:
            config_class = ENGINE_CONFIG_REGISTRY.get(engine_name)
            if not config_class:
                raise ValueError(f"引擎 '{engine_name}' 的配置模型未在元数据中注册。")
            instance = config_class()
            setattr(self.config.engine_configs, engine_name, instance)

    def _create_engine_instance(self, engine_name: str) -> BaseTranslationEngine[Any]:
        """根据引擎名称创建并返回一个翻译引擎的实例。"""
        engine_class = ENGINE_REGISTRY[engine_name]
        engine_config_instance = getattr(self.config.engine_configs, engine_name, None)

        if not engine_config_instance:
            raise ValueError(f"未能为引擎 '{engine_name}' 创建或找到配置实例。")

        return engine_class(config=engine_config_instance)

    def switch_engine(self, engine_name: str) -> None:
        """在运行时切换当前的活动翻译引擎。"""
        if engine_name == self.config.active_engine:
            return

        logger.info("正在切换活动引擎...", new_engine=engine_name)
        if engine_name not in ENGINE_REGISTRY:
            raise ValueError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        self._ensure_engine_config(engine_name)

        # 更新配置中的活动引擎名称
        self.config.active_engine = engine_name
        logger.info(f"成功切换活动引擎至: '{self.config.active_engine}'。")

    async def initialize(self) -> None:
        """
        初始化协调器，主要包括连接持久化存储和执行自愈检查。
        这是一个幂等操作。
        """
        if self.initialized:
            return
        logger.info("正在连接持久化存储...")
        await self.handler.connect()
        await self.handler.reset_stale_tasks()
        self.initialized = True
        logger.info("持久化存储连接成功并完成自愈检查。")

    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """
        处理指定语言的待翻译任务，并以异步生成器方式返回翻译结果。

        此方法将任务编排委托给注入的处理策略。

        返回:
            一个异步生成器，逐一产出 `TranslationResult` 对象。
        """
        validate_lang_codes([target_lang])

        # 决定最终的批处理大小
        active_engine = self.processing_context.active_engine
        engine_batch_policy = getattr(
            active_engine.config, "max_batch_size", self.config.batch_size
        )
        final_batch_size = min(
            batch_size or self.config.batch_size, engine_batch_policy
        )

        logger.info(
            "开始处理待翻译任务。", target_lang=target_lang, batch_size=final_batch_size
        )

        # 从持久化层流式获取任务
        content_batches = self.handler.stream_translatable_items(
            lang_code=target_lang,
            statuses=[TranslationStatus.PENDING, TranslationStatus.FAILED],
            batch_size=final_batch_size,
            limit=limit,
        )

        async for batch in content_batches:
            if not batch:
                continue

            # 按上下文哈希分组，确保同一批次的上下文一致性
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

                # **核心委托点**：调用策略处理批次
                batch_results = await self.processing_policy.process_batch(
                    items_group, target_lang, self.processing_context
                )

                # 保存结果并更新源时间戳
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
        active_engine = self.processing_context.active_engine

        await self.handler.ensure_pending_translations(
            text_content=text_content,
            target_langs=target_langs,
            business_id=business_id,
            context_hash=context_hash,
            context_json=context_json,
            source_lang=(source_lang or self.config.source_lang),
            engine_version=active_engine.VERSION,
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
        """
        提交一个新的翻译请求，将其加入待处理队列。

        此方法应用了并发节流，并支持强制重翻。
        """
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
        """
        立即获取一个已完成的翻译结果。

        它会依次查找内存缓存和持久化存储。如果都未找到，则返回 None。
        """
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
                engine=f"{self.config.active_engine} (mem-cached)",
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
        """
        执行垃圾回收，清理超过指定天数未被访问的源数据及其关联的孤立内容。

        返回:
            一个包含已删除记录统计信息的字典。
        """
        days = expiration_days or self.config.gc_retention_days
        logger.info("开始执行垃圾回收。", expiration_days=days, dry_run=dry_run)
        deleted_counts = await self.handler.garbage_collect(
            retention_days=days, dry_run=dry_run
        )
        logger.info("垃圾回收执行完毕。", deleted_counts=deleted_counts)
        return deleted_counts

    async def close(self) -> None:
        """安全地关闭协调器及其管理的资源（如数据库连接）。"""
        if self.initialized:
            logger.info("正在关闭协调器...")
            await self.handler.close()
            self.initialized = False
            logger.info("协调器已成功关闭。")
