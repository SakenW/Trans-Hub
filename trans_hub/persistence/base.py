# trans_hub/persistence/base.py
# [v2.4 Refactor] 持久化基类重构，实现 rev/head 模型的核心业务逻辑。
# 本基类作为 PostgreSQL 和 SQLite 实现的共享蓝图。
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub._uida.encoder import generate_uid_components
from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import (
    ThContent,
    ThLocalesFallbacks,
    ThProjects,
    ThResolveCache,
    ThTm,
    ThTmLinks,
    ThTransHead,
    ThTransRev,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class BasePersistenceHandler(PersistenceHandler, ABC):
    """持久化处理器的基类，使用 SQLAlchemy ORM Session 实现 UIDA 共享逻辑。"""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], is_sqlite: bool):
        self._sessionmaker = sessionmaker
        self._is_sqlite = is_sqlite
        self._notification_task: asyncio.Task | None = None

    @abstractmethod
    async def connect(self) -> None:
        """[子类实现] 确保与数据库的连接是活跃的。"""
        ...

    async def close(self) -> None:
        """[通用实现] 安全地关闭 SQLAlchemy 引擎及其底层连接池。"""
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
        
        engine = self._sessionmaker.kw.get("bind")
        if engine:
            await engine.dispose()
        logger.info("持久化层引擎已关闭。")

    @abstractmethod
    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[子类实现] 监听数据库通知。"""
        ...

    async def get_content_id_by_uida(
        self, project_id: str, namespace: str, keys_sha256_bytes: bytes
    ) -> str | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThContent.id).where(
                    ThContent.project_id == project_id,
                    ThContent.namespace == namespace,
                    ThContent.keys_sha256_bytes == keys_sha256_bytes,
                )
                return (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"按 UIDA 获取 content_id 失败: {e}") from e

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        content_version: int,
    ) -> str:
        keys_b64, _, keys_sha = generate_uid_components(keys)
        try:
            async with self._sessionmaker.begin() as session:
                # 步骤 1: 确保项目存在
                project_stmt = pg_insert(ThProjects).values(
                    project_id=project_id, display_name=project_id
                ).on_conflict_do_nothing(constraint="th_projects_pkey")
                await session.execute(project_stmt)

                # 步骤 2: Upsert 内容
                values = dict(
                    project_id=project_id,
                    namespace=namespace,
                    keys_sha256_bytes=keys_sha,
                    keys_b64=keys_b64,
                    keys_json=keys,
                    source_payload_json=source_payload,
                    content_version=content_version,
                )
                stmt = pg_insert(ThContent).values(values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_content_uida",
                    set_=dict(
                        source_payload_json=stmt.excluded.source_payload_json,
                        content_version=stmt.excluded.content_version,
                        updated_at=func.now()
                    ),
                )
                await session.execute(stmt)

                # 步骤 3: 获取 content_id
                content_id = await self.get_content_id_by_uida(project_id, namespace, keys_sha)
                if not content_id:
                    raise DatabaseError("Upsert content 后未能获取 content_id")
                return content_id
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert content 失败: {e}") from e
    
    async def get_or_create_translation_head(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
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
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    status=TranslationStatus.DRAFT.value,
                    revision_no=0,
                )
                session.add(initial_rev)
                await session.flush()

                new_head = ThTransHead(
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    current_rev_id=initial_rev.id,
                    current_status=TranslationStatus.DRAFT.value,
                    current_no=0,
                )
                session.add(new_head)
                await session.flush()
                return new_head.id, 0
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取或创建翻译头记录失败: {e}") from e

    async def create_new_translation_revision(
        self,
        *,
        head_id: str,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
        status: TranslationStatus,
        revision_no: int,
        translated_payload: dict[str, Any] | None = None,
        engine_name: str | None = None,
        engine_version: str | None = None,
    ) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                new_rev = ThTransRev(
                    project_id=project_id,
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    status=status.value,
                    revision_no=revision_no,
                    translated_payload_json=translated_payload,
                    engine_name=engine_name,
                    engine_version=engine_version,
                )
                session.add(new_rev)
                await session.flush()

                await session.execute(
                    update(ThTransHead)
                    .where(ThTransHead.id == head_id)
                    .values(
                        current_rev_id=new_rev.id,
                        current_status=status.value,
                        current_no=revision_no,
                    )
                )
                return new_rev.id
        except SQLAlchemyError as e:
            raise DatabaseError(f"创建新翻译修订失败: {e}") from e
            
    async def find_tm_entry(
        self,
        project_id: str,
        namespace: str,
        reuse_sha256_bytes: bytes,
        source_lang: str,
        target_lang: str,
        variant_key: str,
        policy_version: int,
        hash_algo_version: int,
    ) -> tuple[str, dict[str, Any]] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTm.id, ThTm.translated_json).where(
                    ThTm.project_id == project_id,
                    ThTm.namespace == namespace,
                    ThTm.reuse_sha256_bytes == reuse_sha256_bytes,
                    ThTm.source_lang == source_lang,
                    ThTm.target_lang == target_lang,
                    ThTm.variant_key == variant_key,
                    ThTm.policy_version == policy_version,
                    ThTm.hash_algo_version == hash_algo_version,
                )
                result = (await session.execute(stmt)).first()
                return (result.id, result.translated_json) if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"查找 TM 条目失败: {e}") from e

    async def upsert_tm_entry(self, **kwargs: Any) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                values = kwargs.copy()
                values["last_used_at"] = datetime.now(timezone.utc)
                stmt = pg_insert(ThTm).values(**values)
                update_values = {
                    "translated_json": stmt.excluded.translated_json,
                    "quality_score": stmt.excluded.quality_score,
                    "last_used_at": stmt.excluded.last_used_at,
                    "updated_at": func.now(),
                }
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_tm_reuse_key", set_=update_values
                )
                await session.execute(stmt)
                
                select_stmt = select(ThTm.id).where(
                    ThTm.project_id == kwargs["project_id"],
                    ThTm.namespace == kwargs["namespace"],
                    ThTm.reuse_sha256_bytes == kwargs["reuse_sha256_bytes"],
                    ThTm.source_lang == kwargs["source_lang"],
                    ThTm.target_lang == kwargs["target_lang"],
                    ThTm.variant_key == kwargs["variant_key"],
                )
                return (await session.execute(select_stmt)).scalar_one()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert TM entry 失败: {e}") from e

    async def link_translation_to_tm(self, translation_rev_id: str, tm_id: str) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                stmt = pg_insert(ThTmLinks).values(translation_rev_id=translation_rev_id, tm_id=tm_id)
                stmt = stmt.on_conflict_do_nothing(constraint="uq_tm_links_pair")
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"链接 TM 失败: {e}") from e

    async def publish_revision(self, revision_id: str) -> bool:
        try:
            async with self._sessionmaker.begin() as session:
                rev_stmt = select(ThTransRev).where(ThTransRev.id == revision_id)
                rev = (await session.execute(rev_stmt)).scalar_one_or_none()
                if not rev or rev.status != TranslationStatus.REVIEWED.value:
                    logger.warning("发布失败: 修订不存在或状态不是 'reviewed'", revision_id=revision_id, status=getattr(rev, 'status', None))
                    return False

                await session.execute(
                    update(ThTransRev)
                    .where(ThTransRev.id == revision_id)
                    .values(status=TranslationStatus.PUBLISHED.value)
                )

                update_head_stmt = (
                    update(ThTransHead)
                    .where(
                        ThTransHead.content_id == rev.content_id,
                        ThTransHead.target_lang == rev.target_lang,
                        ThTransHead.variant_key == rev.variant_key,
                    )
                    .values(
                        published_rev_id=rev.id,
                        published_no=rev.revision_no,
                        published_at=datetime.now(timezone.utc),
                        current_rev_id=rev.id,
                        current_status=TranslationStatus.PUBLISHED.value,
                        current_no=rev.revision_no
                    )
                )
                result = await session.execute(update_head_stmt)
                return result.rowcount > 0
        except IntegrityError:
            logger.warning("发布失败: 可能由于唯一约束（已有已发布版本）", revision_id=revision_id, exc_info=True)
            return False
        except SQLAlchemyError as e:
            raise DatabaseError(f"发布修订失败: {e}") from e

    async def reject_revision(self, revision_id: str) -> bool:
        try:
            async with self._sessionmaker.begin() as session:
                stmt = update(ThTransRev).where(ThTransRev.id == revision_id).values(status=TranslationStatus.REJECTED.value)
                result = await session.execute(stmt)
                
                if result.rowcount > 0:
                    rev_res = await session.execute(select(ThTransRev).where(ThTransRev.id == revision_id))
                    rev = rev_res.scalar_one()
                    await session.execute(update(ThTransHead).where(
                        ThTransHead.content_id == rev.content_id,
                        ThTransHead.target_lang == rev.target_lang,
                        ThTransHead.variant_key == rev.variant_key,
                        ThTransHead.current_rev_id == revision_id
                    ).values(current_status=TranslationStatus.REJECTED.value))
                return result.rowcount > 0
        except SQLAlchemyError as e:
            raise DatabaseError(f"拒绝修订失败: {e}") from e

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

    async def get_fallback_order(
        self, project_id: str, locale: str
    ) -> list[str] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThLocalesFallbacks.fallback_order).where(
                    ThLocalesFallbacks.project_id == project_id,
                    ThLocalesFallbacks.locale == locale,
                )
                return (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"获取回退顺序失败: {e}") from e

    async def _build_content_items_from_orm(
        self, session: AsyncSession, head_results: list[ThTransHead]
    ) -> list[ContentItem]:
        if not head_results:
            return []

        content_ids = {h.content_id for h in head_results}
        content_stmt = select(ThContent).where(ThContent.id.in_(content_ids))
        contents = {c.id: c for c in (await session.execute(content_stmt)).scalars()}

        items = []
        for head in head_results:
            content_obj = contents.get(head.content_id)
            if content_obj:
                items.append(
                    ContentItem(
                        translation_id=head.current_rev_id,
                        head_id=head.id,
                        revision_no=head.current_no,
                        content_id=content_obj.id,
                        project_id=content_obj.project_id,
                        namespace=content_obj.namespace,
                        source_payload=content_obj.source_payload_json,
                        source_lang=None, # 源语言在 rev 表中，Worker 流程中若需要可单独查询
                        target_lang=head.target_lang,
                        variant_key=head.variant_key,
                    )
                )
        return items

    async def run_garbage_collection(
        self,
        archived_content_retention_days: int,
        unused_tm_retention_days: int,
        dry_run: bool = False,
    ) -> dict[str, int]:
        stats = {"deleted_archived_content": 0, "deleted_unused_tm_entries": 0}
        now = datetime.now(timezone.utc)

        try:
            async with self._sessionmaker.begin() as session:
                if archived_content_retention_days >= 0:
                    cutoff_content = now - timedelta(days=archived_content_retention_days)
                    content_stmt = delete(ThContent).where(
                        ThContent.archived_at.is_not(None),
                        ThContent.archived_at < cutoff_content,
                    )
                    if dry_run:
                        count_stmt = select(func.count()).select_from(content_stmt.alias())
                        stats["deleted_archived_content"] = (await session.execute(count_stmt)).scalar_one() or 0
                    else:
                        result = await session.execute(content_stmt)
                        stats["deleted_archived_content"] = result.rowcount

                if unused_tm_retention_days >= 0:
                    cutoff_tm = now - timedelta(days=unused_tm_retention_days)
                    tm_stmt = delete(ThTm).where(
                        ThTm.last_used_at.is_not(None),
                        ThTm.last_used_at < cutoff_tm,
                    )
                    if dry_run:
                        count_stmt = select(func.count()).select_from(tm_stmt.alias())
                        stats["deleted_unused_tm_entries"] = (await session.execute(count_stmt)).scalar_one() or 0
                    else:
                        result = await session.execute(tm_stmt)
                        stats["deleted_unused_tm_entries"] = result.rowcount

                if dry_run:
                    await session.rollback()
        except SQLAlchemyError as e:
            raise DatabaseError(f"垃圾回收失败: {e}") from e

        return stats