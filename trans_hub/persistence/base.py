# trans_hub/persistence/base.py
"""
提供一个包含所有共享数据库逻辑的、基于 SQLAlchemy ORM Session 的基类。
此基类遵循白皮书 Final v1.2。
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub._uida.encoder import (
    generate_uid_components,
    get_canonical_json_for_debug,
)
from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import ThContent, ThTm, ThTmLinks, ThTranslations

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class BasePersistenceHandler(PersistenceHandler, ABC):
    """持久化处理器的基类，使用 SQLAlchemy ORM Session 实现 UIDA 共享逻辑。"""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker
        self._is_sqlite = self._sessionmaker.kw["bind"].dialect.name == "sqlite"
        self._notification_task: asyncio.Task | None = None

    @abstractmethod
    async def connect(self) -> None:
        """[子类实现] 确保与数据库的连接是活跃的。"""
        ...

    async def close(self) -> None:
        """[通用实现] 安全地关闭 SQLAlchemy 引擎及其底层连接池。"""
        if self._notification_task and not self._notification_task.done():
            self._notification_task.cancel()
        await self._sessionmaker.kw["bind"].dispose()

    @abstractmethod
    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[子类实现] 监听数据库通知。"""
        ...

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
                # 尝试插入
                stmt = insert(ThContent).values(
                    project_id=project_id,
                    namespace=namespace,
                    keys_sha256_bytes=keys_sha,
                    keys_b64=keys_b64,
                    keys_json_debug=get_canonical_json_for_debug(keys),
                    source_payload_json=source_payload,
                    content_version=content_version,
                )
                if self._is_sqlite:
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["project_id", "namespace", "keys_sha256_bytes"]
                    )
                else:
                    stmt = stmt.on_conflict_on_constraint("uq_content_uida", do_nothing=True)
                await session.execute(stmt)

                # 无论插入或冲突，都查询 ID
                select_stmt = select(ThContent.id).where(
                    ThContent.project_id == project_id,
                    ThContent.namespace == namespace,
                    ThContent.keys_sha256_bytes == keys_sha,
                )
                result = await session.execute(select_stmt)
                content_id = result.scalar_one()
                return content_id
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert content failed: {e}") from e

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
                return result if result else None
        except SQLAlchemyError as e:
            raise DatabaseError(f"Find TM entry failed: {e}") from e

    async def upsert_tm_entry(
        self,
        project_id: str,
        namespace: str,
        reuse_sha256_bytes: bytes,
        source_lang: str,
        target_lang: str,
        variant_key: str,
        policy_version: int,
        hash_algo_version: int,
        source_text_json: dict[str, Any],
        translated_json: dict[str, Any],
        quality_score: float,
    ) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                values = dict(
                    project_id=project_id,
                    namespace=namespace,
                    reuse_sha256_bytes=reuse_sha256_bytes,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    policy_version=policy_version,
                    hash_algo_version=hash_algo_version,
                    source_text_json=source_text_json,
                    translated_json=translated_json,
                    quality_score=quality_score,
                    last_used_at=datetime.now(timezone.utc),
                )
                stmt = insert(ThTm).values(values)
                
                update_values = {
                    "translated_json": stmt.excluded.translated_json,
                    "quality_score": stmt.excluded.quality_score,
                    "last_used_at": stmt.excluded.last_used_at,
                    "updated_at": func.now(),
                }
                
                index_elements = [
                    "project_id", "namespace", "reuse_sha256_bytes",
                    "source_lang", "target_lang", "variant_key",
                    "policy_version", "hash_algo_version"
                ]
                
                if self._is_sqlite:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=index_elements, set_=update_values
                    )
                else:
                    stmt = stmt.on_conflict_on_constraint("uq_tm_reuse_key", do_update=update_values)
                
                await session.execute(stmt)

                select_stmt = select(ThTm.id).where(
                    *(getattr(ThTm, col) == values[col] for col in index_elements)
                )
                result = await session.execute(select_stmt)
                return result.scalar_one()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Upsert TM entry failed: {e}") from e

    async def create_draft_translation(
        self,
        project_id: str,
        content_id: str,
        target_lang: str,
        variant_key: str,
        source_lang: str | None,
    ) -> str:
        try:
            async with self._sessionmaker.begin() as session:
                new_draft = ThTranslations(
                    project_id=project_id, # App layer must provide this for SQLite
                    content_id=content_id,
                    target_lang=target_lang,
                    variant_key=variant_key,
                    source_lang=source_lang,
                    status=TranslationStatus.DRAFT.value,
                )
                session.add(new_draft)
                await session.flush()
                return new_draft.id
        except IntegrityError: # Already exists, just return the ID
             async with self._sessionmaker() as session:
                stmt = select(ThTranslations.id).where(
                    ThTranslations.content_id == content_id,
                    ThTranslations.target_lang == target_lang,
                    ThTranslations.variant_key == variant_key,
                    ThTranslations.status == TranslationStatus.DRAFT.value,
                )
                return (await session.execute(stmt)).scalar_one()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Create draft translation failed: {e}") from e

    async def update_translation(
        self,
        translation_id: str,
        status: TranslationStatus,
        translated_payload: dict[str, Any] | None = None,
        tm_id: str | None = None,
        engine_name: str | None = None,
        engine_version: str | None = None,
    ) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                values_to_update = {"status": status.value}
                if translated_payload is not None:
                    values_to_update["translated_payload_json"] = translated_payload
                if tm_id is not None:
                    values_to_update["tm_id"] = tm_id
                if engine_name is not None:
                    values_to_update["engine_name"] = engine_name
                if engine_version is not None:
                    values_to_update["engine_version"] = engine_version

                stmt = (
                    update(ThTranslations)
                    .where(ThTranslations.id == translation_id)
                    .values(**values_to_update)
                )
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"Update translation failed: {e}") from e

    async def link_translation_to_tm(self, translation_id: str, tm_id: str) -> None:
        try:
            async with self._sessionmaker.begin() as session:
                stmt = insert(ThTmLinks).values(translation_id=translation_id, tm_id=tm_id)
                if self._is_sqlite:
                    stmt = stmt.on_conflict_do_nothing(index_elements=["translation_id", "tm_id"])
                else:
                    stmt = stmt.on_conflict_on_constraint("uq_tm_links_pair", do_nothing=True)
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"Link translation to TM failed: {e}") from e

    async def get_published_translation(
        self, content_id: str, target_lang: str, variant_key: str
    ) -> dict[str, Any] | None:
        try:
            async with self._sessionmaker() as session:
                stmt = select(ThTranslations.translated_payload_json).where(
                    ThTranslations.content_id == content_id,
                    ThTranslations.target_lang == target_lang,
                    ThTranslations.variant_key == variant_key,
                    ThTranslations.status == "published",
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Get published translation failed: {e}") from e

    async def _build_content_items_from_orm(
        self, session: AsyncSession, orm_results: list[ThTranslations]
    ) -> list[ContentItem]:
        if not orm_results:
            return []
        
        content_ids = {obj.content_id for obj in orm_results}
        content_stmt = select(ThContent).where(ThContent.id.in_(content_ids))
        contents = {c.id: c for c in (await session.execute(content_stmt)).scalars()}

        items = []
        for orm_obj in orm_results:
            content_obj = contents.get(orm_obj.content_id)
            if content_obj:
                items.append(
                    ContentItem(
                        translation_id=orm_obj.id,
                        content_id=content_obj.id,
                        project_id=content_obj.project_id,
                        namespace=content_obj.namespace,
                        source_payload=content_obj.source_payload_json,
                        source_lang=orm_obj.source_lang,
                        target_lang=orm_obj.target_lang,
                        variant_key=orm_obj.variant_key,
                    )
                )
        return items

    async def run_garbage_collection(
        self,
        archived_content_retention_days: int,
        unused_tm_retention_days: int,
        dry_run: bool = False,
    ) -> dict[str, int]:
        stats = {
            "deleted_archived_content": 0,
            "deleted_unused_tm_entries": 0,
        }
        now = datetime.now(timezone.utc)

        try:
            async with self._sessionmaker.begin() as session:
                # 1. 清理已归档的内容
                if archived_content_retention_days >= 0:
                    cutoff_content = now - timedelta(days=archived_content_retention_days)
                    content_stmt = delete(ThContent).where(
                        ThContent.archived_at != None,
                        ThContent.archived_at < cutoff_content,
                    )
                    if dry_run:
                        count_stmt = select(func.count()).select_from(content_stmt.alias())
                        stats["deleted_archived_content"] = (await session.execute(count_stmt)).scalar_one()
                    else:
                        result = await session.execute(content_stmt)
                        stats["deleted_archived_content"] = result.rowcount

                # 2. 清理长期未使用的 TM 条目
                if unused_tm_retention_days >= 0:
                    cutoff_tm = now - timedelta(days=unused_tm_retention_days)
                    tm_stmt = delete(ThTm).where(
                        ThTm.last_used_at != None,
                        ThTm.last_used_at < cutoff_tm,
                    )
                    if dry_run:
                        count_stmt = select(func.count()).select_from(tm_stmt.alias())
                        stats["deleted_unused_tm_entries"] = (await session.execute(count_stmt)).scalar_one()
                    else:
                        result = await session.execute(tm_stmt)
                        stats["deleted_unused_tm_entries"] = result.rowcount

                if dry_run:
                    await session.rollback()
        except SQLAlchemyError as e:
            raise DatabaseError(f"Garbage collection failed: {e}") from e

        return stats