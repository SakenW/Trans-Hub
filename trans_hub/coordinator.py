# trans_hub/coordinator.py
"""本模块包含 Trans-Hub 引擎的主协调器 (UIDA 架构版)。"""
import asyncio
from typing import Any

import structlog

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.config import TransHubConfig
from trans_hub.context import ProcessingContext
from trans_hub.core import (
    ConfigurationError,
    ContentItem,
    EngineNotFoundError,
    PersistenceHandler,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.engine_registry import ENGINE_REGISTRY
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.policies.processing import DefaultProcessingPolicy, ProcessingPolicy

logger = structlog.get_logger(__name__)


class Coordinator:
    """异步主协调器，是 Trans-Hub UIDA 功能的中心枢纽。"""

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
    ):
        self.config = config
        self.handler = persistence_handler
        self.initialized = False
        self._engine_instances: dict[str, BaseTranslationEngine[Any]] = {}
        self._shutting_down = False
        self._active_tasks: set[asyncio.Task[Any]] = set()

        # ProcessingContext 不再需要 cache
        self.processing_context = ProcessingContext(
            config=self.config,
            handler=self.handler,
        )
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()

    async def initialize(self) -> None:
        """初始化协调器，包括连接数据库和初始化活动引擎。"""
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        await self.handler.connect()
        # await self.handler.reset_stale_tasks() # UIDA 下需要重新设计此逻辑
        
        # 引擎初始化逻辑保持不变
        active_engine_instance = self._get_or_create_engine_instance(
            self.config.active_engine.value
        )
        if not active_engine_instance.initialized:
            await active_engine_instance.initialize()

        self.initialized = True
        logger.info("协调器初始化完成。")

    async def close(self) -> None:
        """优雅地关闭协调器和所有相关资源。"""
        if self._shutting_down or not self.initialized:
            return
        logger.info("开始优雅停机...")
        self._shutting_down = True
        
        # 取消活动任务
        if self._active_tasks:
            for task in list(self._active_tasks):
                task.cancel()
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        # 关闭引擎实例
        await asyncio.gather(
            *[eng.close() for eng in self._engine_instances.values()],
            return_exceptions=True
        )
        
        await self.handler.close()
        self.initialized = False
        logger.info("优雅停机完成。")

    async def request(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        source_lang: str,
        target_langs: list[str],
        content_version: int = 1,
        variant_key: str = '-',
    ) -> None:
        """
        [UIDA] 提交一个新的翻译请求。
        实现“TM 优先”逻辑：若命中 TM，则直接完成；若未命中，则创建后台任务。
        """
        # 步骤 1: 确保内容在数据库中存在，并获取其唯一 ID
        content_id = await self.handler.upsert_content(
            project_id, namespace, keys, source_payload, content_version
        )
        
        # 步骤 2: 准备复用检查
        # 注意: 真实的复用策略应从 namespace_registry.json 加载
        reuse_policy = {"include_source_fields": ["text"]}
        source_fields_for_reuse = {
            k: normalize_plain_text_for_reuse(source_payload.get(k))
            for k in reuse_policy.get("include_source_fields", [])
        }
        # 注意: 真实的降维 keys 逻辑需要从 namespace_registry.json 加载策略
        reduced_keys = {}  # 简化处理
        reuse_sha = build_reuse_sha256(
            namespace=namespace,
            reduced_keys=reduced_keys,
            source_fields=source_fields_for_reuse,
        )

        # 步骤 3: 遍历所有目标语言
        for lang in target_langs:
            # 3a: 尝试从翻译记忆库 (TM) 中查找
            tm_hit = await self.handler.find_tm_entry(
                project_id, namespace, reuse_sha, source_lang, lang,
                variant_key, policy_version=1, hash_algo_version=1
            )
            
            # 3b: 为该语言创建一个翻译记录（无论是否命中TM）
            translation_id = await self.handler.create_draft_translation(
                project_id, content_id, lang, variant_key, source_lang
            )

            if tm_hit:
                # 3c: 如果 TM 命中，直接用 TM 结果更新翻译记录，并建立链接
                tm_id, translated_payload = tm_hit
                await self.handler.update_translation_from_tm(
                    translation_id, tm_id, translated_payload,
                    status=TranslationStatus.REVIEWED # TM 复用的内容直接进入待审
                )
                await self.handler.link_translation_to_tm(translation_id, tm_id)
                logger.info("TM 命中，直接创建待审阅翻译", translation_id=translation_id, tm_id=tm_id)
            else:
                # 3d: 如果 TM 未命中，记录保持 draft 状态，等待 worker 处理
                # 在 PostgreSQL 中，这可能会触发一个 NOTIFY 事件
                logger.info("TM 未命中，已创建翻译草稿任务", translation_id=translation_id)

    # _get_or_create_engine_instance 和其他辅助方法保持不变 (为简洁省略)
    def _get_or_create_engine_instance(self, engine_name: str) -> BaseTranslationEngine[Any]:
        if engine_name not in self._engine_instances:
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(f"引擎 '{engine_name}' 未在引擎注册表中找到。")
            
            engine_config_data = self.config.engine_configs.get(engine_name, {})
            engine_config = engine_class.CONFIG_MODEL(**engine_config_data)
            self._engine_instances[engine_name] = engine_class(config=engine_config)
            logger.info("引擎实例已创建", engine_name=engine_name)
        return self._engine_instances[engine_name]

    async def run_garbage_collection(
        self,
        archived_content_retention_days: int = 90,
        unused_tm_retention_days: int = 365,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """
        运行垃圾回收，清理旧的、无关联的数据。
        这是一个传递给持久化层的操作性方法。
        """
        if not self.initialized:
            raise RuntimeError("Coordinator is not initialized.")
        
        logger.info("开始执行垃圾回收...", dry_run=dry_run)
        report = await self.handler.run_garbage_collection(
            archived_content_retention_days,
            unused_tm_retention_days,
            dry_run
        )
        logger.info("垃圾回收执行完毕。", report=report)
        return report