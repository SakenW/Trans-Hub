# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
v3.0 更新：适配 v3.0 Schema 和新的持久化层接口。
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
from trans_hub.utils import get_context_hash

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
            "协调器初始化开始...", available_engines=list(ENGINE_REGISTRY.keys())
        )
        for engine_name_str, config_class in ENGINE_CONFIG_REGISTRY.items():
            if (
                not hasattr(self.config.engine_configs, engine_name_str)
                or getattr(self.config.engine_configs, engine_name_str) is None
            ):
                instance = config_class()
                setattr(self.config.engine_configs, engine_name_str, instance)
        if self.config.active_engine.value not in ENGINE_REGISTRY:
            raise EngineNotFoundError(
                f"指定的活动引擎 '{self.config.active_engine.value}' 不可用。"
            )
        active_engine_instance = self._get_or_create_engine_instance(
            self.config.active_engine.value
        )
        if active_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ConfigurationError(
                f"活动引擎 '{self.config.active_engine.value}' 需要提供源语言。"
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
    def active_engine(self) -> BaseTranslationEngine[Any]:
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> BaseTranslationEngine[Any]:
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
            self._engine_instances[engine_name] = engine_class(
                config=engine_config_instance
            )
        return self._engine_instances[engine_name]

    def switch_engine(self, engine_name: str) -> None:
        if engine_name == self.config.active_engine.value:
            return
        logger.info("正在切换活动引擎...", new_engine=engine_name)
        if engine_name not in ENGINE_REGISTRY:
            raise EngineNotFoundError(f"尝试切换至一个不可用的引擎: '{engine_name}'")
        self._get_or_create_engine_instance(engine_name)
        self.config.active_engine = EngineName(engine_name)
        logger.info(f"成功切换活动引擎至: '{self.config.active_engine.value}'。")

    async def initialize(self) -> None:
        if self.initialized:
            return
        await self.handler.connect()
        await self.handler.reset_stale_tasks()
        init_tasks = [
            self._get_or_create_engine_instance(name).initialize()
            for name in ENGINE_REGISTRY.keys()
        ]
        await asyncio.gather(*init_tasks)
        self.initialized = True

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
        """轻量级地“报活”一批业务ID，以防止其被垃圾回收。"""
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
            await asyncio.gather(*close_tasks)
            await self.handler.close()
            self.initialized = False
