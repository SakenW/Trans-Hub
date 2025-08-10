# packages/server/src/trans_hub/infrastructure/persistence/_base.py
"""
持久化处理器的基类，封装了使用 SQLAlchemy ORM 实现的、
跨数据库方言共享的核心数据访问逻辑。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub.infrastructure.db._schema import (
    ThContent,
    ThLocalesFallbacks,
    ThProjects,
    ThResolveCache,
    ThTm,
    ThTmLinks,
    ThTransComment,
    ThTransEvent,
    ThTransHead,
    ThTransRev,
)
from trans_hub_core.exceptions import DatabaseError
from trans_hub_core.interfaces import PersistenceHandler
from trans_hub_core.types import Comment, ContentItem, Event, TranslationHead, TranslationStatus
from trans_hub_uida import generate_uida

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = structlog.get_logger(__name__)


class BasePersistenceHandler(PersistenceHandler, ABC):
    """持久化处理器的共享基类。"""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    @abstractmethod
    async def connect(self) -> None:
        """[子类实现] 确保与数据库的连接是活跃的，并执行方言特定的初始化。"""

    async def close(self) -> None:
        engine = self._sessionmaker.kw.get("bind")
        if engine:
            await engine.dispose()
        logger.info("持久化层引擎已关闭。")

    @abstractmethod
    def _get_upsert_stmt(self, model: Any, values: dict[str, Any], constraint: str, update_cols: list[str]) -> Any:
        """[子类实现] 返回方言特定的原子化 upsert 语句。"""

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        content_version: int,
    ) -> str:
        uida = generate_uida(keys)
        try:
            async with self._sessionmaker.begin() as session:
                project_values = {"project_id": project_id, "display_name": project_id}
                project_stmt = self._get_upsert_stmt(ThProjects, project_values, "th_projects_pkey", ["display_name"])
                await session.execute(project_stmt)

                content_values = {
                    "project_id": project_id,
                    "namespace": namespace,
                    "keys_sha256_bytes": uida.keys_sha256_bytes,
                    "keys_b64": uida.keys_b64,
                    "keys_json": keys,
                    "source_payload_json": source_payload,
                    "content_version": content_version,
                }
                content_stmt = self._get_upsert_stmt(
                    ThContent, content_values, "uq_content_uida", ["source_payload_json", "content_version"]
                ).returning(ThContent.id)
                content_id = (await session.execute(content_stmt)).scalar_one()
                return content_id
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert content 失败: {e}") from e

    async def get_or_create_translation_head(
        self, project_id: str, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, int]:
        try:
            async with self._sessionmaker.begin() as session:
                select_stmt = select(ThTransHead.id, ThTransHead.current_no).where(
                    ThTransHead.project_id == project_id,
                    ThTransHead.content_id == content_id,
                    ThTransHead.target_lang == target_lang,
                    ThTransHead.variant_key == variant_key,
                )
                result = (await session.execute(select_stmt)).first()
                if result:
                    return result.id, result.current_no

                initial_rev = ThTransRev(
                    project_id=project_id, content_id=content_id, target_lang=target_lang,
                    variant_key=variant_key, status=TranslationStatus.DRAFT.value, revision_no=0,
                )
                session.add(initial_rev)
                await session.flush()

                new_head = ThTransHead(
                    project_id=project_id, content_id=content_id, target_lang=target_lang,
                    variant_key=variant_key, current_rev_id=initial_rev.id,
                    current_status=TranslationStatus.DRAFT.value, current_no=0,
                )
                session.add(new_head)
                await session.flush()
                return new_head.id, 0
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取或创建翻译头记录失败: {e}") from e

    async def create_new_translation_revision(
        self, *, head_id: str, project_id: str, content_id: str, **kwargs: Any
    ) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                # `kwargs` will contain status, revision_no, etc.
                new_rev = ThTransRev(project_id=project_id, content_id=content_id, **kwargs)
                session.add(new_rev)
                await session.flush()

                await session.execute(
                    update(ThTransHead)
                    .where(ThTransHead.id == head_id)
                    .values(
                        current_rev_id=new_rev.id,
                        current_status=new_rev.status,
                        current_no=new_rev.revision_no,
                    )
                )
                return new_rev.id
        except SQLAlchemyError as e:
            raise DatabaseError(f"创建新翻译修订失败: {e}") from e

    async def find_tm_entry(
        self, *, project_id: str, namespace: str, reuse_sha: bytes, **kwargs: Any
    ) -> tuple[str, dict[str, Any]] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTm.id, ThTm.translated_json).where(
                    ThTm.project_id == project_id,
                    ThTm.namespace == namespace,
                    ThTm.reuse_sha256_bytes == reuse_sha,
                    **kwargs
                )
                result = (await session.execute(stmt)).first()
                return (result.id, result.translated_json) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"查找 TM 条目失败: {e}") from e

    async def upsert_tm_entry(self, *, project_id: str, **kwargs: Any) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                values = {"project_id": project_id, "last_used_at": datetime.now(timezone.utc), **kwargs}
                stmt = self._get_upsert_stmt(
                    ThTm, values, "uq_tm_reuse_key", ["translated_json", "quality_score", "last_used_at"]
                ).returning(ThTm.id)
                tm_id = (await session.execute(stmt)).scalar_one()
                return tm_id
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert TM entry 失败: {e}") from e

    async def link_translation_to_tm(
        self, translation_rev_id: str, tm_id: str, project_id: str
    ) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                values = {
                    "project_id": project_id,
                    "translation_rev_id": translation_rev_id,
                    "tm_id": tm_id,
                }
                stmt = self._get_upsert_stmt(ThTmLinks, values, "uq_tm_links_triplet", [])
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"链接 TM 失败: {e}") from e
    
    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> tuple[str, dict[str, Any]] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTransHead.published_rev_id, ThTransRev.translated_payload_json)
                    .join(ThTransRev, ThTransHead.published_rev_id == ThTransRev.id)
                    .where(
                        ThTransHead.content_id == content_id,
                        ThTransHead.target_lang == target_lang,
                        ThTransHead.variant_key == variant_key,
                        ThTransHead.published_rev_id.is_not(None),
                    )
                )
                result = (await session.execute(stmt)).first()
                return (result.published_rev_id, result.translated_payload_json) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取已发布翻译失败: {e}") from e

    async def publish_revision(self, revision_id: str) -> bool:
        try:
            async with self._sessionmaker.begin() as session:
                rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == revision_id))).scalar_one_or_none()
                if not rev or rev.status != TranslationStatus.REVIEWED.value:
                    logger.warning("发布失败: 修订不存在或状态不是 'reviewed'", rev_id=revision_id, status=getattr(rev, "status", None))
                    return False

                await session.execute(
                    update(ThTransRev).where(ThTransRev.id == revision_id).values(status=TranslationStatus.PUBLISHED.value)
                )

                update_head_stmt = (
                    update(ThTransHead)
                    .where(
                        ThTransHead.content_id == rev.content_id,
                        ThTransHead.target_lang == rev.target_lang,
                        ThTransHead.variant_key == rev.variant_key,
                    )
                    .values(
                        published_rev_id=rev.id, published_no=rev.revision_no,
                        published_at=datetime.now(timezone.utc),
                        current_rev_id=rev.id, current_status=TranslationStatus.PUBLISHED.value,
                        current_no=rev.revision_no,
                    )
                )
                result = await session.execute(update_head_stmt)
                return result.rowcount > 0
        except IntegrityError:
            logger.warning("发布失败: 可能由于唯一约束（已有已发布版本）", rev_id=revision_id, exc_info=True)
            return False
        except SQLAlchemyError as e:
            raise DatabaseError(f"发布修订失败: {e}") from e

    async def reject_revision(self, revision_id: str) -> bool:
        try:
            async with self._sessionmaker.begin() as session:
                stmt = update(ThTransRev).where(ThTransRev.id == revision_id).values(status=TranslationStatus.REJECTED.value)
                result = await session.execute(stmt)

                if result.rowcount > 0:
                    rev = (await session.execute(select(ThTransRev).where(ThTransRev.id == revision_id))).scalar_one()
                    await session.execute(
                        update(ThTransHead)
                        .where(ThTransHead.current_rev_id == revision_id)
                        .values(current_status=TranslationStatus.REJECTED.value)
                    )
                return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseError(f"拒绝修订失败: {e}") from e

    async def write_event(self, event: Event) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                session.add(ThTransEvent(**event.model_dump(exclude={"id", "created_at"}, exclude_none=True)))
        except SQLAlchemyError as e:
            raise DatabaseError(f"写入事件失败: {e}") from e

    async def add_comment(self, comment: Comment) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                new_comment = ThTransComment(**comment.model_dump(exclude={"id", "created_at"}, exclude_none=True))
                session.add(new_comment)
                await session.flush()
                return new_comment.id
        except SQLAlchemyError as e:
            raise DatabaseError(f"添加评论失败: {e}") from e

    async def get_comments(self, head_id: str) -> list[Comment]:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTransComment).where(ThTransComment.head_id == head_id).order_by(ThTransComment.created_at)
                results = (await session.execute(stmt)).scalars().all()
                return [Comment.from_orm(r) for r in results]
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取评论失败: {e}") from e

    async def get_fallback_order(self, project_id: str, locale: str) -> list[str] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThLocalesFallbacks.fallback_order).where(
                    ThLocalesFallbacks.project_id == project_id, ThLocalesFallbacks.locale == locale
                )
                return (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取回退顺序失败: {e}") from e

    async def set_fallback_order(self, project_id: str, locale: str, fallback_order: list[str]) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                values = {"project_id": project_id, "locale": locale, "fallback_order": fallback_order}
                stmt = self._get_upsert_stmt(ThLocalesFallbacks, values, "th_locales_fallbacks_pkey", ["fallback_order"])
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"设置回退顺序失败: {e}") from e

    async def get_translation_head_by_uida(
        self, *, project_id: str, namespace: str, keys: dict[str, Any], target_lang: str, variant_key: str
    ) -> TranslationHead | None:
        uida = generate_uida(keys)
        try:
            async with self._sessionmaker() as session:
                content_id = (await session.execute(select(ThContent.id).where(
                    ThContent.project_id == project_id, ThContent.namespace == namespace,
                    ThContent.keys_sha256_bytes == uida.keys_sha256_bytes
                ))).scalar_one_or_none()
                if not content_id: return None

                stmt = select(ThTransHead).where(
                    ThTransHead.content_id == content_id,
                    ThTransHead.target_lang == target_lang,
                    ThTransHead.variant_key == variant_key
                )
                result = (await session.execute(stmt)).scalar_one_or_none()
                return TranslationHead.from_orm(result) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过UIDA获取Head失败: {e}") from e

    async def get_head_by_id(self, head_id: str) -> TranslationHead | None:
        try:
            async with self._sessionmaker() as session:
                result = (await session.execute(select(ThTransHead).where(ThTransHead.id == head_id))).scalar_one_or_none()
                return TranslationHead.from_orm(result) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过ID获取Head失败: {e}") from e

    async def get_head_by_revision(self, revision_id: str) -> TranslationHead | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTransHead).where(
                    (ThTransHead.current_rev_id == revision_id) | (ThTransHead.published_rev_id == revision_id)
                ).limit(1)
                result = (await session.execute(stmt)).scalar_one_or_none()
                return TranslationHead.from_orm(result) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"通过Revision获取Head失败: {e}") from e
    
    async def _build_content_items_from_orm(
        self, session: AsyncSession, head_results: list[ThTransHead]
    ) -> list[ContentItem]:
        """根据一批 Head ORM 对象，高效地构建出 ContentItem DTO 列表。"""
        if not head_results:
            return []

        content_ids = {h.content_id for h in head_results}
        content_map = {
            c.id: c for c in (
                await session.execute(select(ThContent).where(ThContent.id.in_(content_ids)))
            ).scalars()
        }

        items = []
        for head in head_results:
            content = content_map.get(head.content_id)
            if content:
                items.append(
                    ContentItem(
                        head_id=head.id, current_rev_id=head.current_rev_id,
                        current_no=head.current_no, content_id=content.id,
                        project_id=content.project_id, namespace=content.namespace,
                        source_payload=content.source_payload_json,
                        source_lang="en", # TODO: Get from content or project
                        target_lang=head.target_lang, variant_key=head.variant_key,
                    )
                )
        return items

    async def _stream_drafts_query(
        self, session: AsyncSession, batch_size: int, **kwargs: Any
    ) -> list[ThTransHead]:
        """执行查询 'draft' 状态 head 的核心 SQLAlchemy 语句。"""
        stmt = (
            select(ThTransHead)
            .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
            .order_by(ThTransHead.updated_at)
            .limit(batch_size)
        )
        if kwargs:
            stmt = stmt.with_for_update(**kwargs)
        return (await session.execute(stmt)).scalars().all()