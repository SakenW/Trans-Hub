# trans_hub/coordinator.py
"""本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。"""

import asyncio
import json
from collections.abc import AsyncGenerator
from itertools import groupby
from typing import Any, Optional

import structlog

from .cache import TranslationCache
from .config import EngineName, TransHubConfig
from .context import ProcessingContext
from .engine_registry import ENGINE_REGISTRY, discover_engines
from .engines.base import BaseTranslationEngine
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
        """
        初始化协调器。

        Args:
            config (TransHubConfig): Trans-Hub 的主配置对象。
            persistence_handler (PersistenceHandler): 持久化层的实现实例。
            rate_limiter (Optional[RateLimiter]): 可选的速率限制器。
            max_concurrent_requests (Optional[int]): 最大并发请求数。

        """
        discover_engines()
        self.config = config
        self.handler = persistence_handler
        self.cache = TranslationCache(self.config.cache_config)
        self.rate_limiter = rate_limiter
        self.initialized = False
        self._engine_instances: dict[str, BaseTranslationEngine[Any]] = {}
        self._request_semaphore: Optional[asyncio.Semaphore] = None
        if max_concurrent_requests and max_concurrent_requests > 0:
            self._request_semaphore = asyncio.Semaphore(max_concurrent_requests)

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
    def active_engine(self) -> BaseTranslationEngine[Any]:
        """获取当前活动的翻译引擎实例。"""
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> BaseTranslationEngine[Any]:
        """惰性地获取或创建引擎实例。"""
        if engine_name not in self._engine_instances:
            logger.debug("首次请求，正在创建引擎实例...", engine_name=engine_name)
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(
                    f"引擎 '{engine_name}' 未在引擎注册表中找到。"
                )

            engine_config_data = getattr(self.config.engine_configs, engine_name, None)
            if engine_config_data is None:
                # 如果配置中完全没有这个引擎的 section，就用默认值创建
                engine_config_instance = engine_class.CONFIG_MODEL()
            else:
                engine_config_instance = engine_config_data

            self._engine_instances[engine_name] = engine_class(
                config=engine_config_instance
            )
            logger.info("引擎实例创建成功。", engine_name=engine_name)
        return self._engine_instances[engine_name]

    def switch_engine(self, engine_name: str) -> None:
        """切换活动的翻译引擎。"""
        if engine_name == self.config.active_engine.value:
            return

        if engine_name not in ENGINE_REGISTRY:
            raise EngineNotFoundError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        # 在切换时触发惰性加载和验证
        new_engine_instance = self._get_or_create_engine_instance(engine_name)
        if new_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ConfigurationError(f"切换失败：引擎 '{engine_name}' 需要提供源语言。")

        self.config.active_engine = EngineName(engine_name)
        logger.info("成功切换活动引擎。", new_engine=self.config.active_engine.value)

    async def initialize(self) -> None:
        """
        初始化协调器及其所有组件。
        这将验证活动引擎的配置并连接数据库。
        """
        if self.initialized:
            return

        logger.info("协调器初始化开始...")

        # 核心修复：只在初始化时验证活动引擎的配置
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
            raise e  # 重新抛出异常

        await self.handler.connect()
        await self.handler.reset_stale_tasks()

        # 核心修复：正确地 await 协程
        init_tasks = [
            instance.initialize() for instance in self._engine_instances.values()
        ]
        if init_tasks:
            await asyncio.gather(*init_tasks)

        self.initialized = True
        logger.info("协调器初始化完成。", active_engine=self.config.active_engine.value)

    # ... (其余方法保持不变) ...
    async def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
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
            if not batch:
                continue
            batch.sort(key=lambda item: item.context_id or "")
            for _context_id, items_group_iter in groupby(
                batch, key=lambda item: item.context_id
            ):
                items_group = list(items_group_iter)
                batch_results = await self.processing_policy.process_batch(
                    items_group, target_lang, self.processing_context, active_engine
                )
                await self.handler.save_translations(batch_results)
                for result in batch_results:
                    if (
                        result.status == TranslationStatus.TRANSLATED
                        and result.business_id
                    ):
                        await self.touch_jobs([result.business_id])
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

    async def request(
        self,
        target_langs: list[str],
        text_content: str,
        business_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
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

    async def touch_jobs(self, business_ids: list[str]) -> None:
        if not business_ids:
            return
        await self.handler.touch_jobs(business_ids)

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
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
        days = expiration_days or self.config.gc_retention_days
        return await self.handler.garbage_collect(retention_days=days, dry_run=dry_run)

    async def close(self) -> None:
        if self.initialized:
            close_tasks = [
                instance.close() for instance in self._engine_instances.values()
            ]
            if close_tasks:
                await asyncio.gather(*close_tasks)
            await self.handler.close()
            self.initialized = False
