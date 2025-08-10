# trans_hub/coordinator.py
# [v2.4 Refactor] Coordinator 全面升级，适配 rev/head 模型和白皮书 v2.4 流程。
# request/get_translation/publish/reject 等方法均已重构。
import asyncio
from typing import Any

import structlog

from trans_hub._tm.normalizers import normalize_plain_text_for_reuse
from trans_hub._uida.encoder import generate_uid_components
from trans_hub._uida.reuse_key import build_reuse_sha256
from trans_hub.config import TransHubConfig
from trans_hub.core import (
    EngineNotFoundError,
    PersistenceHandler,
    ProcessingContext,
    TranslationStatus,
)
from trans_hub.engine_registry import ENGINE_REGISTRY, discover_engines
from trans_hub.engines.base import BaseTranslationEngine
from trans_hub.policies.processing import DefaultProcessingPolicy, ProcessingPolicy

logger = structlog.get_logger(__name__)


class Coordinator:
    """异步主协调器，是 Trans-Hub 功能的中心枢纽。"""

    def __init__(
        self,
        config: TransHubConfig,
        persistence_handler: PersistenceHandler,
    ):
        self.config = config
        self.handler = persistence_handler
        self.initialized = False
        self._engine_instances: dict[str, BaseTranslationEngine[Any]] = {}
        self.processing_context = ProcessingContext(config=config, handler=self.handler)
        self.processing_policy: ProcessingPolicy = DefaultProcessingPolicy()
        discover_engines()

    async def initialize(self) -> None:
        """初始化协调器及其所有依赖项。"""
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        await self.handler.connect()
        active_engine = self._get_or_create_engine_instance(
            self.config.active_engine.value
        )
        if not active_engine.initialized:
            await active_engine.initialize()
        self.initialized = True
        logger.info("协调器初始化完成。")

    async def close(self) -> None:
        """优雅地关闭协调器及其所有依赖项。"""
        if not self.initialized:
            return
        logger.info("协调器开始优雅停机...")
        await asyncio.gather(
            *[eng.close() for eng in self._engine_instances.values()],
            return_exceptions=True,
        )
        await self.handler.close()
        self.initialized = False
        logger.info("协调器优雅停机完成。")

    async def request(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        target_langs: list[str],
        source_lang: str | None = None,
        content_version: int = 1,
        variant_key: str = "-",
    ) -> None:
        """
        提交一个新的 UIDA 翻译请求。
        实现“TM 优先”逻辑：若命中 TM，则直接完成；若未命中，则创建后台任务。
        """
        final_source_lang = source_lang or self.config.source_lang
        if not final_source_lang:
            raise ValueError("源语言必须在请求或配置中提供。")

        content_id = await self.handler.upsert_content(
            project_id, namespace, keys, source_payload, content_version
        )

        source_fields = {
            "text": normalize_plain_text_for_reuse(source_payload.get("text"))
        }
        reuse_sha = build_reuse_sha256(
            namespace=namespace, reduced_keys={}, source_fields=source_fields
        )

        for lang in target_langs:
            head_id, rev_no = await self.handler.get_or_create_translation_head(
                project_id, content_id, lang, variant_key
            )

            tm_hit = await self.handler.find_tm_entry(
                project_id,
                namespace,
                reuse_sha,
                final_source_lang,
                lang,
                variant_key,
                policy_version=1,
                hash_algo_version=1,
            )

            if tm_hit:
                tm_id, translated_payload = tm_hit
                rev_id = await self.handler.create_new_translation_revision(
                    head_id=head_id,
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=lang,
                    variant_key=variant_key,
                    status=TranslationStatus.REVIEWED,
                    revision_no=rev_no + 1,
                    translated_payload=translated_payload,
                )
                await self.handler.link_translation_to_tm(rev_id, tm_id)
                logger.info(
                    "TM 命中，直接创建待审阅修订", revision_id=rev_id, head_id=head_id
                )
            else:
                await self.handler.create_new_translation_revision(
                    head_id=head_id,
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=lang,
                    variant_key=variant_key,
                    status=TranslationStatus.DRAFT,
                    revision_no=rev_no + 1,
                )
                logger.info("TM 未命中，已创建草稿修订", head_id=head_id)

    async def get_translation(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        target_lang: str,
        variant_key: str = "-",
    ) -> dict[str, Any] | None:
        """获取最终的翻译结果，包含语言和变体回退逻辑。"""
        _, _, keys_sha = generate_uid_components(keys)
        content_id = await self.handler.get_content_id_by_uida(
            project_id, namespace, keys_sha
        )
        if not content_id:
            return None

        result = await self.handler.get_published_translation(
            content_id, target_lang, variant_key
        )
        if result:
            return result[1]

        if variant_key != "-":
            result = await self.handler.get_published_translation(
                content_id, target_lang, "-"
            )
            if result:
                return result[1]

        fallback_order = await self.handler.get_fallback_order(project_id, target_lang)
        if fallback_order:
            for fallback_lang in fallback_order:
                result = await self.handler.get_published_translation(
                    content_id, fallback_lang, "-"
                )
                if result:
                    return result[1]

        return None

    async def publish_translation(self, revision_id: str) -> bool:
        """将一条 'reviewed' 状态的翻译修订发布。"""
        return await self.handler.publish_revision(revision_id)

    async def reject_translation(self, revision_id: str) -> bool:
        """将一条翻译修订的状态设置为 'rejected'。"""
        return await self.handler.reject_revision(revision_id)

    def _get_or_create_engine_instance(
        self, engine_name: str
    ) -> BaseTranslationEngine[Any]:
        if engine_name not in self._engine_instances:
            engine_class = ENGINE_REGISTRY.get(engine_name)
            if not engine_class:
                raise EngineNotFoundError(
                    f"引擎 '{engine_name}' 未在引擎注册表中找到。"
                )

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
        """运行垃圾回收。"""
        if not self.initialized:
            raise RuntimeError("Coordinator 未初始化。")

        logger.info("开始执行垃圾回收...", dry_run=dry_run)
        report = await self.handler.run_garbage_collection(
            archived_content_retention_days, unused_tm_retention_days, dry_run
        )
        logger.info("垃圾回收执行完毕。", report=report)
        return report
