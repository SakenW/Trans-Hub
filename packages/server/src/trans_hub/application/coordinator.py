# packages/server/src/trans_hub/application/coordinator.py
"""
Trans-Hub 应用服务总协调器。

这是 `trans-hub-server` 包对外暴露的核心公共 API。
它封装了所有复杂的业务流程，为上层（如 CLI, API, SDK）提供简单、
一致的方法调用。
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from trans_hub.domain import tm as tm_domain
from trans_hub.infrastructure.db._session import create_db_engine, create_db_sessionmaker
from trans_hub.infrastructure.persistence import create_persistence_handler
from trans_hub.infrastructure.redis.cache import RedisCacheHandler
from trans_hub.infrastructure.redis.streams import RedisStreamProducer
from trans_hub_core.exceptions import EngineNotFoundError
from trans_hub_core.types import Comment, Event, TranslationStatus
from trans_hub_uida import generate_uida

from .events import CommentAdded, TMApplied, TranslationPublished, TranslationRejected, TranslationSubmitted
from .processors import TranslationProcessor

if TYPE_CHECKING:
    from trans_hub.config import TransHubConfig
    # from trans_hub.infrastructure.engines.base import BaseTranslationEngine
    from trans_hub_core.interfaces import CacheHandler, PersistenceHandler, StreamProducer
    from trans_hub_core.types import TranslationHead

logger = structlog.get_logger(__name__)


class Coordinator:
    """
    异步主协调器，是 Trans-Hub 功能的中心枢纽。
    """
    
    def __init__(self, config: TransHubConfig):
        """
        初始化协调器。

        注意：这是一个同步方法。所有需要 I/O 的初始化都应在 `initialize` 方法中完成。
        """
        self.config = config
        self._engine = create_db_engine(config)
        self._sessionmaker = create_db_sessionmaker(self._engine)
        
        self.handler: PersistenceHandler = create_persistence_handler(config, self._sessionmaker)
        
        self.stream_producer: StreamProducer | None = None
        self.cache: CacheHandler | None = None
        
        # 延迟初始化 processor，等待 stream_producer
        self.processor: TranslationProcessor | None = None
        
        self._engine_instances: dict[str, Any] = {} # BaseTranslationEngine
        self.initialized = False

    async def initialize(self) -> None:
        """
        异步初始化协调器及其所有依赖项。
        包括数据库连接、Redis 连接和引擎初始化。
        """
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        
        await self.handler.connect()

        if self.config.redis_url:
            from trans_hub.infrastructure.redis._client import get_redis_client
            redis_client = await get_redis_client(self.config)
            self.stream_producer = RedisStreamProducer(redis_client)
            self.cache = RedisCacheHandler(redis_client)
            logger.info("Redis 基础设施已初始化 (Stream, Cache)。")

        # 现在可以安全地初始化 processor
        self.processor = TranslationProcessor(
            self.handler, self.stream_producer, self.config.worker.event_stream_name
        )
        
        # from trans_hub.infrastructure.engines import discover_engines
        # discover_engines()

        self.initialized = True
        logger.info("协调器初始化完成。")

    async def close(self) -> None:
        """优雅地关闭协调器及其所有依赖项。"""
        if not self.initialized:
            return
        logger.info("协调器开始优雅停机...")
        await asyncio.gather(
            *[eng.close() for eng in self._engine_instances.values()],
            self.handler.close(),
            return_exceptions=True,
        )
        if self.config.redis_url:
            from trans_hub.infrastructure.redis._client import close_redis_client
            await close_redis_client()

        self.initialized = False
        logger.info("协调器优雅停机完成。")

    async def _publish_event(self, event: Event) -> None:
        """发布一个业务事件到事件流并持久化到数据库。"""
        await self.handler.write_event(event)
        if self.stream_producer:
            await self.stream_producer.publish(
                self.config.worker.event_stream_name,
                event.model_dump(mode="json")
            )

    async def request_translation(
        self, *, project_id: str, namespace: str, keys: dict[str, Any],
        source_payload: dict[str, Any], target_langs: list[str],
        source_lang: str | None = None, actor: str = "system",
        **kwargs: Any
    ) -> str:
        final_source_lang = source_lang or self.config.default_source_lang
        if not final_source_lang:
            raise ValueError("源语言必须在请求或配置中提供。")

        content_id = await self.handler.upsert_content(
            project_id=project_id, namespace=namespace, keys=keys,
            source_payload=source_payload, content_version=kwargs.get("content_version", 1)
        )

        source_text_for_tm = source_payload.get("text", "")
        source_fields = {"text": tm_domain.normalize_text_for_tm(source_text_for_tm)}
        reuse_sha = tm_domain.build_reuse_key(
            namespace=namespace, reduced_keys={}, source_fields=source_fields
        )

        for lang in target_langs:
            variant_key = kwargs.get("variant_key", "-")
            head_id, rev_no = await self.handler.get_or_create_translation_head(
                project_id, content_id, lang, variant_key
            )
            await self._publish_event(TranslationSubmitted(
                head_id=head_id, project_id=project_id, actor=actor
            ))

            tm_hit = await self.handler.find_tm_entry(
                project_id=project_id, namespace=namespace, reuse_sha=reuse_sha,
                source_lang=final_source_lang, target_lang=lang, variant_key=variant_key,
                policy_version=1, hash_algo_version=1
            )

            if tm_hit:
                tm_id, translated_payload = tm_hit
                rev_id = await self.handler.create_new_translation_revision(
                    head_id=head_id, project_id=project_id, content_id=content_id,
                    target_lang=lang, variant_key=variant_key,
                    status=TranslationStatus.REVIEWED, revision_no=rev_no + 1,
                    translated_payload_json=translated_payload, origin_lang="tm"
                )
                await self.handler.link_translation_to_tm(rev_id, tm_id, project_id)
                await self._publish_event(TMApplied(
                    head_id=head_id, project_id=project_id, actor="system", payload={"tm_id": tm_id}
                ))
            else:
                await self.handler.create_new_translation_revision(
                    head_id=head_id, project_id=project_id, content_id=content_id,
                    target_lang=lang, variant_key=variant_key,
                    status=TranslationStatus.DRAFT, revision_no=rev_no + 1
                )
        return content_id
    
    async def get_translation(
        self, *, project_id: str, namespace: str, keys: dict[str, Any],
        target_lang: str, variant_key: str = "-"
    ) -> dict[str, Any] | None:
        uida = generate_uida(keys)
        content_id = await self.handler.get_content_id_by_uida(
            project_id, namespace, uida.keys_sha256_bytes
        )
        if not content_id:
            return None

        cache_key = f"resolve:{content_id}:{target_lang}:{variant_key}"
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug("解析缓存命中", key=cache_key)
                return cached_result

        result_payload, _ = await self._resolve_from_db_with_fallback(
            project_id, content_id, target_lang, variant_key
        )

        if result_payload and self.cache:
            await self.cache.set(cache_key, result_payload, ttl=self.config.default_resolve_ttl_seconds)
            logger.debug("解析结果已写入缓存", key=cache_key)
        
        return result_payload

    async def _resolve_from_db_with_fallback(
        self, project_id: str, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        result = await self.handler.get_published_translation(content_id, target_lang, variant_key)
        if result: return result[1], result[0]

        if variant_key != "-":
            result = await self.handler.get_published_translation(content_id, target_lang, "-")
            if result: return result[1], result[0]

        fallback_order = await self.handler.get_fallback_order(project_id, target_lang)
        if fallback_order:
            for fallback_lang in fallback_order:
                result = await self.handler.get_published_translation(content_id, fallback_lang, "-")
                if result: return result[1], result[0]
        
        return None, None

    async def publish_translation(self, revision_id: str, actor: str = "system") -> bool:
        head = await self.handler.get_head_by_revision(revision_id)
        if not head:
            return False

        success = await self.handler.publish_revision(revision_id)
        if success:
            await self._publish_event(TranslationPublished(
                head_id=head.id, project_id=head.project_id, actor=actor,
                payload={"revision_id": revision_id}
            ))
        return success

    async def reject_translation(self, revision_id: str, actor: str = "system") -> bool:
        head = await self.handler.get_head_by_revision(revision_id)
        if not head:
            return False

        success = await self.handler.reject_revision(revision_id)
        if success:
            await self._publish_event(TranslationRejected(
                head_id=head.id, project_id=head.project_id, actor=actor,
                payload={"revision_id": revision_id}
            ))
        return success

    async def add_comment(self, head_id: str, author: str, body: str) -> str:
        head = await self.handler.get_head_by_id(head_id)
        if not head:
            raise ValueError(f"Head ID '{head_id}' 不存在。")
        
        comment = Comment(head_id=head_id, project_id=head.project_id, author=author, body=body)
        comment_id = await self.handler.add_comment(comment)
        
        await self._publish_event(CommentAdded(
            head_id=head_id, project_id=head.project_id, actor=author,
            payload={"comment_id": comment_id}
        ))
        return comment_id

    async def get_comments(self, head_id: str) -> list[Comment]:
        return await self.handler.get_comments(head_id)