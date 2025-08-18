# packages/server/src/trans_hub/application/coordinator.py
"""
Trans-Hub 应用服务总协调器。(v3.2.2 仓库修复和逻辑加固版)
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import structlog

from sqlalchemy import update
from trans_hub.infrastructure.db._schema import ThTransRev, ThTransHead

from trans_hub.domain import tm as tm_domain
from trans_hub.application.resolvers import TranslationResolver
from trans_hub_core.types import Comment, Event, TranslationStatus
from trans_hub_uida import generate_uida
from .events import (
    CommentAdded,
    TMApplied,
    TranslationPublished,
    TranslationRejected,
    TranslationUnpublished,
    TranslationSubmitted,
)

if TYPE_CHECKING:
    from trans_hub.infrastructure.uow import UowFactory
    from trans_hub.config import TransHubConfig
    from trans_hub_core.interfaces import CacheHandler, StreamProducer
    from trans_hub_core.uow import IUnitOfWork

logger = structlog.get_logger(__name__)


class Coordinator:
    """异步主协调器，是 Trans-Hub 功能的中心枢纽。"""

    def __init__(
        self,
        config: TransHubConfig,
        uow_factory: UowFactory,
        stream_producer: StreamProducer | None = None,
        cache: CacheHandler | None = None,
    ):
        self.config = config
        self._uow_factory = uow_factory
        self.stream_producer = stream_producer
        self.cache = cache
        self.resolver = TranslationResolver(uow_factory)
        self.initialized = False

    async def initialize(self) -> None:
        """异步初始化协调器。"""
        if self.initialized:
            return
        logger.info("协调器初始化开始...")
        self.initialized = True
        logger.info("协调器初始化完成。")

    async def close(self) -> None:
        """优雅地关闭协调器。"""
        if not self.initialized:
            return
        logger.info("协调器优雅停机完成。")

    async def _publish_event(self, uow: IUnitOfWork, event: Event) -> None:
        """将事件写入事务性发件箱。"""
        await uow.outbox.add(
            topic=self.config.worker.event_stream_name,
            payload=event.model_dump(mode="json"),
        )

    async def request_translation(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        target_langs: list[str],
        source_lang: str | None = None,
        actor: str = "system",
        **kwargs: Any,
    ) -> str:
        final_source_lang = source_lang or self.config.default_source_lang
        if not final_source_lang:
            raise ValueError("源语言必须在请求或配置中提供。")

        uida = generate_uida(keys)

        async with self._uow_factory() as uow:
            await uow.misc.add_project_if_not_exists(project_id, project_id)

            content_id = await uow.content.get_id_by_uida(
                project_id, namespace, uida.keys_sha256_bytes
            )
            if content_id:
                await uow.content.update_payload(content_id, source_payload)
            else:
                content_id = await uow.content.add(
                    project_id=project_id,
                    namespace=namespace,
                    keys_sha256_bytes=uida.keys_sha256_bytes,
                    source_lang=final_source_lang,
                    source_payload_json=source_payload,
                )

            source_text_for_tm = source_payload.get("text", "")
            source_fields = {
                "text": tm_domain.normalize_text_for_tm(source_text_for_tm)
            }
            reuse_sha = tm_domain.build_reuse_key(
                namespace=namespace, reduced_keys={}, source_fields=source_fields
            )

            for lang in target_langs:
                variant_key = kwargs.get("variant_key", "-")
                head_id, rev_no = await uow.translations.get_or_create_head(
                    project_id, content_id, lang, variant_key
                )
                await self._publish_event(
                    uow,
                    TranslationSubmitted(
                        head_id=head_id, project_id=project_id, actor=actor
                    ),
                )

                tm_hit = await uow.tm.find_entry(
                    project_id=project_id,
                    namespace=namespace,
                    reuse_sha=reuse_sha,
                    src_lang=final_source_lang,
                    tgt_lang=lang,
                    variant_key=variant_key,
                )

                if tm_hit:
                    tm_id, translated_payload = tm_hit
                    rev_id = await uow.translations.create_revision(
                        head_id=head_id,
                        project_id=project_id,
                        content_id=content_id,
                        target_lang=lang,
                        variant_key=variant_key,
                        status=TranslationStatus.REVIEWED,
                        revision_no=rev_no + 1,
                        translated_payload_json=translated_payload,
                        origin_lang="tm",
                    )
                    await uow.tm.link_revision_to_tm(rev_id, tm_id, project_id)
                    await self._publish_event(
                        uow,
                        TMApplied(
                            head_id=head_id,
                            project_id=project_id,
                            actor="system",
                            payload={"tm_id": tm_id},
                        ),
                    )
        return content_id

    async def get_translation(
        self,
        *,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        target_lang: str,
        variant_key: str = "-",
    ) -> dict[str, Any] | None:
        uida = generate_uida(keys)

        async with self._uow_factory() as uow:
            content_id = await uow.content.get_id_by_uida(
                project_id, namespace, uida.keys_sha256_bytes
            )
            if not content_id:
                logger.debug(
                    "内容未找到 (UIDA miss)", project_id=project_id, namespace=namespace
                )
                return None

        cache_key = f"{self.config.redis.key_prefix}resolve:{content_id}:{target_lang}:{variant_key}"
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.debug("解析缓存命中", key=cache_key)
                return cached_result

        result_payload, _ = await self.resolver.resolve_with_fallback(
            project_id, content_id, target_lang, variant_key
        )

        if result_payload and self.cache:
            ttl = (
                self.config.redis.cache.ttl
                if self.config.redis and self.config.redis.cache
                else 3600
            )
            await self.cache.set(cache_key, result_payload, ttl=ttl)
            logger.debug("解析结果已写入缓存", key=cache_key)

        return result_payload

    async def publish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj or rev_obj.status != TranslationStatus.REVIEWED:
                return False

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if not head_obj:
                return False

            await uow.session.execute(
                update(ThTransRev)
                .where(ThTransRev.id == revision_id)
                .values(status=TranslationStatus.PUBLISHED.value)
            )

            await uow.session.execute(
                update(ThTransHead)
                .where(ThTransHead.id == head_obj.id)
                .values(
                    published_rev_id=revision_id,
                    published_no=rev_obj.revision_no,
                    published_at=datetime.now(timezone.utc),
                    current_rev_id=revision_id,
                    current_status=TranslationStatus.PUBLISHED.value,
                    current_no=rev_obj.revision_no,
                )
            )

            await self._publish_event(
                uow,
                TranslationPublished(
                    head_id=head_obj.id,
                    project_id=head_obj.project_id,
                    actor=actor,
                    payload={"revision_id": revision_id},
                ),
            )
        return True

    async def unpublish_translation(
        self, revision_id: str, actor: str = "system"
    ) -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj or rev_obj.status != TranslationStatus.PUBLISHED:
                return False

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if not head_obj or head_obj.published_rev_id != revision_id:
                return False

            await uow.session.execute(
                update(ThTransRev)
                .where(ThTransRev.id == revision_id)
                .values(status=TranslationStatus.REVIEWED.value)
            )

            await uow.session.execute(
                update(ThTransHead)
                .where(ThTransHead.id == head_obj.id)
                .values(
                    published_rev_id=None,
                    published_no=None,
                    published_at=None,
                    current_status=TranslationStatus.REVIEWED.value,
                )
            )

            await self._publish_event(
                uow,
                TranslationUnpublished(
                    head_id=head_obj.id,
                    project_id=head_obj.project_id,
                    actor=actor,
                    payload={"revision_id": revision_id},
                ),
            )
        return True

    async def reject_translation(self, revision_id: str, actor: str = "system") -> bool:
        async with self._uow_factory() as uow:
            rev_obj = await uow.translations.get_revision_by_id(revision_id)
            if not rev_obj:
                return False

            result = await uow.session.execute(
                update(ThTransRev)
                .where(ThTransRev.id == revision_id)
                .values(status=TranslationStatus.REJECTED.value)
            )
            if result.rowcount == 0:
                return False

            await uow.session.execute(
                update(ThTransHead)
                .where(ThTransHead.current_rev_id == revision_id)
                .values(current_status=TranslationStatus.REJECTED.value)
            )

            head_obj = await uow.translations.get_head_by_revision(revision_id)
            if head_obj:
                await self._publish_event(
                    uow,
                    TranslationRejected(
                        head_id=head_obj.id,
                        project_id=head_obj.project_id,
                        actor=actor,
                        payload={"revision_id": revision_id},
                    ),
                )
        return True

    async def add_comment(self, head_id: str, author: str, body: str) -> str:
        async with self._uow_factory() as uow:
            head = await uow.translations.get_head_by_id(head_id)
            if not head:
                raise ValueError(f"翻译头 ID '{head_id}' 不存在。")

            comment = Comment(
                head_id=head_id, project_id=head.project_id, author=author, body=body
            )
            comment_id = await uow.misc.add_comment(comment)

            await self._publish_event(
                uow,
                CommentAdded(
                    head_id=head_id,
                    project_id=head.project_id,
                    actor=author,
                    payload={"comment_id": comment_id},
                ),
            )
        return comment_id

    async def get_comments(self, head_id: str) -> list[Comment]:
        async with self._uow_factory() as uow:
            return await uow.misc.get_comments(head_id)
