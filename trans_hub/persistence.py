# trans_hub/persistence.py (终极完美版)
"""提供了 Trans-Hub 的默认持久化实现，基于 aiosqlite。
此版本为纯异步设计，移除了不必要的锁以提升并发性能，并强化了封装。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite
import structlog

from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class DefaultPersistenceHandler(PersistenceHandler):
    """使用 aiosqlite 实现的、高性能的异步持久化处理器。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        try:
            self._conn = await aiosqlite.connect(self.db_path, isolation_level=None)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON;")
            await self._conn.execute("PRAGMA journal_mode = WAL;")
            logger.info("数据库连接已建立", db_path=self.db_path)
        except aiosqlite.Error:
            logger.error("连接数据库失败", exc_info=True)
            raise

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("数据库未连接或已关闭。请先调用 connect()。")
        return self._conn

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Cursor, None]:
        if self._conn is None:
            raise ConnectionError("Database not connected.")
        cursor = await self._conn.cursor()
        try:
            await cursor.execute("BEGIN")
            yield cursor
            await cursor.execute("COMMIT")
        except Exception:
            logger.error("事务执行失败，正在回滚", exc_info=True)
            if self._conn:
                await cursor.execute("ROLLBACK")
            raise
        finally:
            await cursor.close()

    async def ensure_pending_translations(
        self,
        text_content: str,
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        business_id: Optional[str] = None,
        context_hash: Optional[str] = None,
        context_json: Optional[str] = None,
    ) -> None:
        async with self.transaction() as cursor:
            await cursor.execute(
                "SELECT id FROM th_content WHERE value = ?", (text_content,)
            )
            row = await cursor.fetchone()
            content_id = row["id"] if row else None
            if not content_id:
                await cursor.execute(
                    "INSERT INTO th_content (value) VALUES (?)", (text_content,)
                )
                content_id = cursor.lastrowid

            if not content_id:
                raise RuntimeError("无法为翻译任务确定 content_id。")

            if business_id:
                sql = """
                    INSERT INTO th_sources (business_id, content_id, context_hash, last_seen_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(business_id) DO UPDATE SET
                    content_id = excluded.content_id, context_hash = excluded.context_hash,
                    last_seen_at = excluded.last_seen_at;"""
                now = datetime.now(timezone.utc)
                await cursor.execute(
                    sql, (business_id, content_id, context_hash, now.isoformat())
                )

            insert_sql = "INSERT OR IGNORE INTO th_translations (content_id, lang_code, context_hash, status, source_lang_code, engine_version, context) VALUES (?, ?, ?, ?, ?, ?, ?)"

            params_to_insert = []
            for lang in target_langs:
                await cursor.execute(
                    "SELECT status FROM th_translations WHERE content_id=? AND lang_code=? AND context_hash=?",
                    (content_id, lang, context_hash),
                )
                existing = await cursor.fetchone()
                if (
                    existing
                    and existing["status"] == TranslationStatus.TRANSLATED.value
                ):
                    continue
                params_to_insert.append(
                    (
                        content_id,
                        lang,
                        context_hash,
                        TranslationStatus.PENDING.value,
                        source_lang,
                        engine_version,
                        context_json,
                    )
                )

            if params_to_insert:
                await cursor.executemany(insert_sql, params_to_insert)
                logger.info(
                    f"为 content_id={content_id} 确保了 {len(params_to_insert)} 个 PENDING 任务。"
                )

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        status_values = tuple(s.value for s in statuses)
        processed_count = 0
        while limit is None or processed_count < limit:
            current_batch_size = min(
                batch_size, limit - processed_count if limit is not None else batch_size
            )
            if current_batch_size <= 0:
                break

            batch_items: list[ContentItem] = []
            async with self.transaction() as cursor:
                find_batch_sql = f"SELECT tr.id, tr.content_id, c.value, tr.context_hash, tr.context FROM th_translations tr JOIN th_content c ON tr.content_id = c.id WHERE tr.lang_code = ? AND tr.status IN ({','.join('?' for _ in status_values)}) ORDER BY tr.last_updated_at ASC LIMIT ?"
                params = [lang_code] + list(status_values) + [current_batch_size]
                await cursor.execute(find_batch_sql, params)
                batch_rows = await cursor.fetchall()

                if not batch_rows:
                    break

                batch_ids = [row["id"] for row in batch_rows]
                update_sql = f"UPDATE th_translations SET status = ?, last_updated_at = ? WHERE id IN ({','.join('?' for _ in batch_ids)})"
                now = datetime.now(timezone.utc)
                await cursor.execute(
                    update_sql,
                    [TranslationStatus.TRANSLATING.value, now.isoformat()] + batch_ids,
                )

                batch_items = [
                    ContentItem(
                        content_id=r["content_id"],
                        value=r["value"],
                        context_hash=r["context_hash"],
                        context=json.loads(r["context"]) if r["context"] else None,
                    )
                    for r in batch_rows
                ]

            if not batch_items:
                break

            yield batch_items
            processed_count += len(batch_items)

    async def save_translations(self, results: list[TranslationResult]) -> None:
        if not results:
            return

        params_to_update = [
            {
                "status": res.status.value,
                "translation_content": res.translated_content,
                "engine": res.engine,
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
                "original_content": res.original_content,
                "lang_code": res.target_lang,
                "context_hash": res.context_hash,
                "current_status": TranslationStatus.TRANSLATING.value,
            }
            for res in results
            if res.original_content
        ]

        if not params_to_update:
            return

        async with self.transaction() as cursor:
            await cursor.executemany(
                """
                UPDATE th_translations SET
                    status = :status, translation_content = :translation_content,
                    engine = :engine, last_updated_at = :last_updated_at
                WHERE
                    lang_code = :lang_code AND context_hash = :context_hash AND status = :current_status
                    AND content_id = (SELECT id FROM th_content WHERE value = :original_content)
            """,
                params_to_update,
            )
            logger.info(f"成功更新了 {cursor.rowcount} 条翻译记录。")

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        context_hash = get_context_hash(context)
        sql = """
            SELECT tr.translation_content, tr.status, tr.engine, s.business_id
            FROM th_translations tr JOIN th_content c ON tr.content_id = c.id
            LEFT JOIN th_sources s ON tr.content_id = s.content_id AND tr.context_hash = s.context_hash
            WHERE c.value = ? AND tr.lang_code = ? AND tr.context_hash = ? AND tr.status = ?"""

        async with self.connection.execute(
            sql,
            (
                text_content,
                target_lang,
                context_hash,
                TranslationStatus.TRANSLATED.value,
            ),
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            return TranslationResult(
                original_content=text_content,
                translated_content=row["translation_content"],
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=row["engine"],
                from_cache=True,
                business_id=row["business_id"],
                context_hash=context_hash,
            )
        return None

    async def get_business_id_for_content(
        self, content_id: int, context_hash: str
    ) -> Optional[str]:
        sql = "SELECT business_id FROM th_sources WHERE content_id = ? AND context_hash = ?"
        async with self.connection.execute(sql, (content_id, context_hash)) as cursor:
            row = await cursor.fetchone()
        return row["business_id"] if row else None

    async def touch_source(self, business_id: str) -> None:
        async with self.transaction() as cursor:
            sql = "UPDATE th_sources SET last_seen_at = ? WHERE business_id = ?"
            now_iso = datetime.now(timezone.utc).isoformat()
            await cursor.execute(sql, (now_iso, business_id))
            if cursor.rowcount > 0:
                logger.debug(
                    "更新了源记录的时间戳",
                    business_id=business_id,
                    last_seen_at=now_iso,
                )

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        if retention_days < 0:
            raise ValueError("retention_days 必须是非负数。")
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()
        stats = {"deleted_sources": 0, "deleted_content": 0}

        async with self.transaction() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) FROM th_sources WHERE last_seen_at < ?", (cutoff,)
            )
            count_row = await cursor.fetchone()
            stats["deleted_sources"] = count_row[0] if count_row else 0
            if not dry_run and stats["deleted_sources"] > 0:
                await cursor.execute(
                    "DELETE FROM th_sources WHERE last_seen_at < ?", (cutoff,)
                )

            orphan_query = "SELECT id FROM th_content c WHERE c.created_at < ? AND NOT EXISTS (SELECT 1 FROM th_sources s WHERE s.content_id = c.id) AND NOT EXISTS (SELECT 1 FROM th_translations t WHERE t.content_id = c.id)"
            await cursor.execute(orphan_query, (cutoff,))
            orphan_ids = [row[0] for row in await cursor.fetchall()]
            stats["deleted_content"] = len(orphan_ids)

            if not dry_run and orphan_ids:
                delete_orphan_sql = f"DELETE FROM th_content WHERE id IN ({','.join('?' for _ in orphan_ids)})"
                await cursor.execute(delete_orphan_sql, orphan_ids)
        return stats

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭", db_path=self.db_path)
