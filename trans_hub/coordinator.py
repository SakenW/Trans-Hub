# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
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
        """
        初始化 Coordinator。

        v3.1 最终修复：将 discover_engines() 的调用恢复到此处，以确保
        任何 Coordinator 实例在创建时都能访问已发现的引擎，这对于非 CLI
        应用场景（如示例脚本）至关重要。

        Args:
            config: Trans-Hub 的主配置对象。
            persistence_handler: 实现了 PersistenceHandler 协议的持久化处理器实例。
            rate_limiter: 可选的速率限制器实例。
            max_concurrent_requests: 可选的最大并发请求数。
        """
        # 确保在创建 Coordinator 实例时，引擎注册表已被填充
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

        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

    # ... (Coordinator 的其余代码保持不变) ...
    @property
    def active_engine(self) -> "BaseTranslationEngine[Any]":
        """获取当前活动的翻译引擎实例。"""
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> "BaseTranslationEngine[Any]":
        """根据引擎名称获取或创建引擎实例（惰性加载）。"""
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
        """切换当前的活动翻译引擎。"""
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
        """处理指定语言的待处理翻译任务。"""
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
                    await self.handler.save_translations(batch_results)
                    for result in batch_results:
                        if (
                            result.status == TranslationStatus.TRANSLATED
                            and result.business_id
                        ):
                            await self.touch_jobs([result.business_id])
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
        """提交一个新的翻译请求。"""
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
        """更新一个或多个业务ID关联任务的 `updated_at` 时间戳。"""
        if not business_ids:
            return
        await self.handler.touch_jobs(business_ids)

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """直接获取一个翻译结果，会依次查找内存缓存和数据库。"""
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
        """运行垃圾回收，清理旧的、无关联的数据。"""
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
        await asyncio.sleep(0.1)
        await self.handler.close()
        self.initialized = False
        logger.info("优雅停机完成。")
