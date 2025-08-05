# trans_hub/coordinator.py
"""
本模块包含 Trans-Hub 引擎的主协调器 (Coordinator)。
v3.0.0 重大更新：
- 适配 v3.0.0 的数据库 Schema 和可插拔的持久层协议。
- 实现“稳定引用ID”和“结构化载荷”原则。
- 内部逻辑上划分出“解析层”与“操作层”的职责。
"""

import asyncio
from collections.abc import AsyncGenerator
from itertools import groupby
from typing import TYPE_CHECKING, Any, Optional, Set

import structlog

from .cache import TranslationCache
from .config import EngineName, TransHubConfig
from .context import ProcessingContext
from .core import (
    ConfigurationError,
    EngineNotFoundError,
    PersistenceHandler,
    TranslationResult,
    TranslationStatus,
)
from .engine_registry import ENGINE_REGISTRY, discover_engines
from .policies import DefaultProcessingPolicy, ProcessingPolicy
from .rate_limiter import RateLimiter

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
        # v3.5.5 修复：使用任务跟踪代替复杂的锁机制
        self._active_tasks: Set[asyncio.Task[Any]] = set()

        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
            cache=self.cache,
            rate_limiter=self.rate_limiter,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

    def _check_is_active(self) -> None:
        """检查协调器是否处于活动状态。"""
        if self._shutting_down or not self.initialized:
            raise RuntimeError("Coordinator is not active (closed or not initialized).")

    @property
    def active_engine(self) -> "BaseTranslationEngine[Any]":
        """获取当前活动的翻译引擎实例。"""
        self._check_is_active()
        return self._get_or_create_engine_instance(self.config.active_engine.value)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> "BaseTranslationEngine[Any]":
        """根据引擎名称获取或创建引擎实例（惰性加载和动态配置解析）。"""
        if engine_name not in self._engine_instances:
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(
                    f"引擎 '{engine_name}' 未在引擎注册表中找到。"
                )

            EngineConfigModel = engine_class.CONFIG_MODEL
            raw_config_data = self.config.engine_configs.get(engine_name, {})
            try:
                engine_config_instance = EngineConfigModel(**raw_config_data)
            except Exception as e:
                raise ConfigurationError(
                    f"解析引擎 '{engine_name}' 的配置失败: {e}"
                ) from e

            self._engine_instances[engine_name] = engine_class(
                config=engine_config_instance
            )
            logger.info("引擎实例创建成功。", engine_name=engine_name)
        return self._engine_instances[engine_name]

    async def switch_engine(self, engine_name: str) -> None:
        """切换当前的活动翻译引擎。"""
        self._check_is_active()
        if engine_name == self.config.active_engine.value:
            return

        if engine_name not in ENGINE_REGISTRY:
            raise EngineNotFoundError(f"尝试切换至一个不可用的引擎: '{engine_name}'")

        new_engine_instance = self._get_or_create_engine_instance(engine_name)
        if new_engine_instance.REQUIRES_SOURCE_LANG and not self.config.source_lang:
            raise ConfigurationError(f"切换失败：引擎 '{engine_name}' 需要提供源语言。")

        if not new_engine_instance.initialized:
            await new_engine_instance.initialize()

        self.config.active_engine = EngineName(engine_name)
        logger.info("成功切换活动引擎。", new_engine=self.config.active_engine.value)

    async def initialize(self) -> None:
        """初始化协调器，包括连接数据库和初始化活动引擎。"""
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        await self.handler.connect()
        await self.handler.reset_stale_tasks()

        init_tasks = [
            instance.initialize()
            for instance in self._engine_instances.values()
            if not instance.initialized
        ]
        active_engine_instance = self._get_or_create_engine_instance(
            self.config.active_engine.value
        )
        if not active_engine_instance.initialized:
            init_tasks.append(active_engine_instance.initialize())

        if init_tasks:
            await asyncio.gather(*list(set(init_tasks)))

        self.initialized = True
        logger.info("协调器初始化完成。", active_engine=self.config.active_engine.value)

    async def _process_and_track(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """[内部] 包装 process_pending_translations 以传播取消信号。"""
        self._check_is_active()
        try:
            async for result in self._internal_process_pending(
                target_lang, batch_size, limit
            ):
                yield result
        except asyncio.CancelledError:
            logger.warning("处理任务被取消。", lang=target_lang)
            raise

    def process_pending_translations(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """[公共] 返回一个异步生成器来处理待处理任务。"""
        return self._process_and_track(target_lang, batch_size, limit)

    async def _internal_process_pending(
        self,
        target_lang: str,
        batch_size: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[TranslationResult, None]:
        """[解析层] 处理指定语言的待处理翻译任务。"""
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

            for _, items_group_iter in groupby(batch, key=lambda item: item.context_id):
                items_group = list(items_group_iter)
                batch_results = await self.processing_policy.process_batch(
                    items_group,
                    target_lang,
                    self.processing_context,
                    active_engine,
                )
                await self.handler.save_translation_results(batch_results)
                for result in batch_results:
                    yield result

    async def request(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        target_langs: list[str],
        context: Optional[dict[str, Any]] = None,
        source_lang: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
        """
        [操作层入口] 提交一个新的翻译请求。
        """
        self._check_is_active()

        op = self._execute_request_operation(
            business_id=business_id,
            source_payload=source_payload,
            target_langs=target_langs,
            context=context,
            source_lang=source_lang,
            force_retranslate=force_retranslate,
        )

        if self._request_semaphore:
            async with self._request_semaphore:
                await op
        else:
            await op

    async def _execute_request_operation(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        target_langs: list[str],
        context: Optional[dict[str, Any]],
        source_lang: Optional[str],
        force_retranslate: bool,
    ) -> None:
        """[操作层实现] 执行翻译请求的核心数据库操作。"""
        content_id, context_id = await self.handler.ensure_content_and_context(
            business_id=business_id,
            source_payload=source_payload,
            context=context,
        )
        await self.handler.create_pending_translations(
            content_id=content_id,
            context_id=context_id,
            target_langs=target_langs,
            source_lang=(source_lang or self.config.source_lang),
            engine_version=self.active_engine.VERSION,
            force_retranslate=force_retranslate,
        )
        logger.info("翻译请求已成功入队", business_id=business_id, langs=target_langs)

    async def get_translation(
        self,
        business_id: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        """
        [解析层] 直接获取一个翻译结果。
        """
        self._check_is_active()
        return await self.handler.find_translation(
            business_id=business_id,
            target_lang=target_lang,
            context=context,
        )

    async def run_garbage_collection(
        self, expiration_days: Optional[int] = None, dry_run: bool = False
    ) -> dict[str, int]:
        """运行垃圾回收，清理旧的、无关联的数据。"""
        self._check_is_active()
        days = expiration_days or self.config.gc_retention_days
        return await self.handler.garbage_collect(retention_days=days, dry_run=dry_run)

    def track_task(self, task: asyncio.Task[Any]) -> None:
        """[公共] 允许外部调用者（如 worker CLI）注册其任务以进行优雅停机。"""
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    async def close(self) -> None:
        """优雅地关闭协调器和所有相关资源。"""
        if self._shutting_down or not self.initialized:
            return

        logger.info("开始优雅停机...")
        self._shutting_down = True

        if self._active_tasks:
            logger.info(f"正在取消 {len(self._active_tasks)} 个活动任务...")
            for task in list(self._active_tasks):
                task.cancel()
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        logger.info("所有活动任务已处理完毕，正在关闭底层资源...")
        close_tasks = [instance.close() for instance in self._engine_instances.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        await self.handler.close()
        self.initialized = False
        logger.info("优雅停机完成。")
