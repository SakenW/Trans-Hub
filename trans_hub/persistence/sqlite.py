# trans_hub/persistence/sqlite.py
# [v2.4.2 Final Fix] 修正 SyntaxError 并为 SQLite 正确实现 upsert 逻辑。
from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trans_hub._uida.encoder import generate_uid_components
from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.types import ContentItem, TranslationStatus
from trans_hub.db.schema import (
    ThContent,
    ThProjects,
    ThTm,
    ThTmLinks,
    ThTransHead,
    ThTransRev,
)
from trans_hub.persistence.base import BasePersistenceHandler

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(BasePersistenceHandler):
    """`PersistenceHandler` 协议的 SQLite 实现。"""

    SUPPORTS_NOTIFICATIONS = False

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], db_path: str):
        super().__init__(sessionmaker, is_sqlite=True)
        self.db_path = db_path

    async def connect(self) -> None:
        """[覆盖] 建立连接并为 SQLite 设置必要的 PRAGMA。"""
        async with self._sessionmaker() as session:
            async with session.begin():
                await session.execute(text("PRAGMA foreign_keys = ON;"))
                if self.db_path != ":memory:":
                    await session.execute(text("PRAGMA journal_mode=WAL;"))
        logger.info("SQLite 数据库连接已建立并通过 PRAGMA 检查", db_path=self.db_path)

    async def upsert_content(
        self,
        project_id: str,
        namespace: str,
        keys: dict[str, Any],
        source_payload: dict[str, Any],
        content_version: int,
    ) -> str:
        """为 SQLite 覆盖 upsert_content，使用 'INSERT OR IGNORE' + 'UPDATE'。"""
        keys_b64, _, keys_sha = generate_uid_components(keys)
        try:
            async with self._sessionmaker.begin() as session:
                # 确保项目存在
                await session.execute(
                    insert(ThProjects)
                    .values(project_id=project_id, display_name=project_id)
                    .prefix_with("OR IGNORE")
                )

                # 尝试插入
                insert_stmt = (
                    insert(ThContent)
                    .values(
                        project_id=project_id,
                        namespace=namespace,
                        keys_sha256_bytes=keys_sha,
                        keys_b64=keys_b64,
                        keys_json=keys,
                        source_payload_json=source_payload,
                        content_version=content_version,
                    )
                    .prefix_with("OR IGNORE")
                )
                await session.execute(insert_stmt)

                # 获取 ID
                content_id = await self.get_content_id_by_uida(
                    project_id, namespace, keys_sha
                )
                if not content_id:
                    raise DatabaseError("SQLite upsert content 失败")

                # 如果是更新（即插入被忽略），则执行 update
                update_stmt = (
                    update(ThContent)
                    .where(ThContent.id == content_id)
                    .values(
                        source_payload_json=source_payload,
                        content_version=content_version,
                        updated_at=func.now(),
                    )
                )
                await session.execute(update_stmt)

                return content_id
        except SQLAlchemyError as e:
            raise DatabaseError(f"SQLite upsert content 失败: {e}") from e

    async def upsert_tm_entry(self, **kwargs: Any) -> str:
        """为 SQLite 覆盖 upsert_tm_entry。"""
        try:
            async with self._sessionmaker.begin() as session:
                unique_constraint_fields = {
                    "project_id": kwargs["project_id"],
                    "namespace": kwargs["namespace"],
                    "reuse_sha256_bytes": kwargs["reuse_sha256_bytes"],
                    "source_lang": kwargs["source_lang"],
                    "target_lang": kwargs["target_lang"],
                    "variant_key": kwargs["variant_key"],
                    "policy_version": kwargs["policy_version"],
                    "hash_algo_version": kwargs["hash_algo_version"],
                }

                find_stmt = select(ThTm.id).filter_by(**unique_constraint_fields)
                existing_id = (await session.execute(find_stmt)).scalar_one_or_none()

                if existing_id:
                    update_values = {
                        "translated_json": kwargs["translated_json"],
                        "quality_score": kwargs["quality_score"],
                        "last_used_at": datetime.now(timezone.utc),
                    }
                    update_stmt = (
                        update(ThTm)
                        .where(ThTm.id == existing_id)
                        .values(**update_values)
                    )
                    await session.execute(update_stmt)
                    return existing_id
                else:
                    insert_stmt = insert(ThTm).values(**kwargs).returning(ThTm.id)
                    result = await session.execute(insert_stmt)
                    return result.scalar_one()
        except SQLAlchemyError as e:
            raise DatabaseError(f"SQLite Upsert TM entry 失败: {e}") from e

    async def link_translation_to_tm(self, translation_rev_id: str, tm_id: str) -> None:
        """为 SQLite 覆盖 link_translation_to_tm。"""
        try:
            async with self._sessionmaker.begin() as session:
                rev = (
                    await session.execute(
                        select(ThTransRev).where(ThTransRev.id == translation_rev_id)
                    )
                ).scalar_one()
                stmt = (
                    insert(ThTmLinks)
                    .values(
                        project_id=rev.project_id,
                        translation_rev_id=translation_rev_id,
                        tm_id=tm_id,
                    )
                    .prefix_with("OR IGNORE")
                )
                await session.execute(stmt)
        except SQLAlchemyError as e:
            raise DatabaseError(f"SQLite 链接 TM 失败: {e}") from e

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] SQLite 不支持 LISTEN/NOTIFY。"""

        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False:
                yield ""

        return _empty_generator()

    async def stream_draft_translations(
        self,
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """为 SQLite 实现无死锁的流式获取。"""
        all_draft_head_ids: list[str] = []
        try:
            async with self._sessionmaker() as session:
                stmt = (
                    select(ThTransHead.id)
                    .where(ThTransHead.current_status == TranslationStatus.DRAFT.value)
                    .order_by(ThTransHead.updated_at)
                )
                if limit:
                    stmt = stmt.limit(limit)
                all_draft_head_ids = (await session.execute(stmt)).scalars().all()
        except Exception as e:
            raise DatabaseError("为 SQLite 获取草稿 ID 失败。") from e

        for i in range(0, len(all_draft_head_ids), batch_size):
            id_batch = all_draft_head_ids[i : i + batch_size]
            items: list[ContentItem] = []
            try:
                async with self._sessionmaker() as session:
                    stmt = select(ThTransHead).where(ThTransHead.id.in_(id_batch))
                    head_results = (await session.execute(stmt)).scalars().all()
                    items = await self._build_content_items_from_orm(
                        session, head_results
                    )
            except Exception:
                logger.error(
                    "为批次获取完整内容失败", batch_ids=id_batch, exc_info=True
                )
                continue

            if items:
                yield items
