# trans_hub/persistence/sqlite.py
"""
提供了基于 aiosqlite 的持久化实现。
此版本修复了 UPSERT 逻辑，以兼容 SQLite 的 ON CONFLICT 限制，并补全了导入。
"""

import json
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# --- 最终、决定性的修复 ---
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

import aiosqlite
import structlog

from trans_hub.exceptions import DatabaseError
from trans_hub.interfaces import PersistenceHandler
from trans_hub.types import (
    GLOBAL_CONTEXT_SENTINEL,
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(PersistenceHandler):
    # ... (所有其他方法都保持不变，我将只粘贴 garbage_collect 和它之前的方法
    # 以确认 上下文) ...
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        try:
            self._conn = await aiosqlite.connect(self.db_path, isolation_level=None)
            self._conn.row_factory = aiosqlite.Row
            logger.info("SQLite 数据库连接已建立", db_path=self.db_path)
        except aiosqlite.Error as e:
            logger.error("连接 SQLite 数据库失败", exc_info=True)
            raise DatabaseError("数据库连接失败") from e

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite 数据库连接已关闭", db_path=self.db_path)

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("数据库未连接或已关闭。请先调用 connect()。")
        return self._conn

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[aiosqlite.Cursor, None]:
        async with self.connection.cursor() as cursor:
            try:
                await cursor.execute("BEGIN")
                yield cursor
                await cursor.execute("COMMIT")
            except Exception:
                logger.error("SQLite 事务执行失败，正在回滚", exc_info=True)
                if self.connection.is_alive():
                    await cursor.execute("ROLLBACK")
                raise

    async def reset_stale_tasks(self) -> None:
        async with self._transaction() as cursor:
            await cursor.execute(
                "UPDATE th_translations SET status = ?, error = NULL WHERE status = ?",
                (
                    TranslationStatus.PENDING.value,
                    TranslationStatus.TRANSLATING.value,
                ),
            )
            if cursor.rowcount > 0:
                logger.warning("系统自愈：重置了遗留的翻译任务", count=cursor.rowcount)

    async def ensure_pending_translations(
        self,
        text_content: str,
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        business_id: Optional[str] = None,
        context_hash: Optional[str] = None,
        context_json: Optional[str] = None,
        force_retranslate: bool = False,
    ) -> None:
        async with self._transaction() as cursor:
            await cursor.execute(
                "SELECT id FROM th_content WHERE value = ?", (text_content,)
            )
            content_row = await cursor.fetchone()
            if content_row:
                content_id = cast(str, content_row["id"])
            else:
                content_id = str(uuid.uuid4())
                await cursor.execute(
                    "INSERT INTO th_content (id, value) VALUES (?, ?)",
                    (content_id, text_content),
                )

            context_id: Optional[str] = None
            if context_hash and context_hash != GLOBAL_CONTEXT_SENTINEL:
                await cursor.execute(
                    "SELECT id FROM th_contexts WHERE context_hash = ?", (context_hash,)
                )
                context_row = await cursor.fetchone()
                if context_row:
                    context_id = cast(str, context_row["id"])
                else:
                    context_id = str(uuid.uuid4())
                    await cursor.execute(
                        "INSERT INTO th_contexts (id, context_hash, value) "
                        "VALUES (?, ?, ?)",
                        (context_id, context_hash, context_json),
                    )

            if business_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                select_sql = (
                    "SELECT id FROM th_jobs WHERE business_id = ? AND content_id = ?"
                )
                params: list[Any] = [business_id, content_id]
                if context_id:
                    select_sql += " AND context_id = ?"
                    params.append(context_id)
                else:
                    select_sql += " AND context_id IS NULL"
                await cursor.execute(select_sql, params)
                job_row = await cursor.fetchone()
                if job_row:
                    await cursor.execute(
                        "UPDATE th_jobs SET last_requested_at = ? WHERE id = ?",
                        (now_iso, job_row["id"]),
                    )
                else:
                    await cursor.execute(
                        "INSERT INTO th_jobs (id, business_id, content_id, context_id, "
                        "last_requested_at) VALUES (?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            business_id,
                            content_id,
                            context_id,
                            now_iso,
                        ),
                    )

            if force_retranslate:
                update_sql = (
                    "UPDATE th_translations SET status = ?, engine_version = ?, "
                    "error = NULL "
                    "WHERE content_id = ? {} AND lang_code IN ({})"
                ).format(
                    "AND context_id = ?" if context_id else "AND context_id IS NULL",
                    ",".join("?" * len(target_langs)),
                )
                update_params: list[Any] = [
                    TranslationStatus.PENDING.value,
                    engine_version,
                    content_id,
                ]
                if context_id:
                    update_params.append(context_id)
                update_params.extend(target_langs)
                await cursor.execute(update_sql, update_params)

            insert_sql = (
                "INSERT OR IGNORE INTO th_translations "
                "(id, content_id, context_id, lang_code, status, "
                "source_lang_code, engine_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
            params_to_insert = [
                (
                    str(uuid.uuid4()),
                    content_id,
                    context_id,
                    lang,
                    TranslationStatus.PENDING.value,
                    source_lang,
                    engine_version,
                )
                for lang in target_langs
            ]
            if params_to_insert:
                await cursor.executemany(insert_sql, params_to_insert)

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
                batch_size,
                (limit - processed_count) if limit is not None else batch_size,
            )
            if current_batch_size <= 0:
                break
            batch_ids: list[str] = []
            async with self._transaction() as cursor:
                placeholders = ",".join("?" for _ in status_values)
                find_ids_sql = (
                    f"SELECT id FROM th_translations "
                    f"WHERE lang_code = ? AND status IN ({placeholders}) "
                    f"ORDER BY last_updated_at ASC LIMIT ?"
                )
                params = [lang_code] + list(status_values) + [current_batch_size]
                await cursor.execute(find_ids_sql, params)
                batch_rows_ids = await cursor.fetchall()
                if not batch_rows_ids:
                    break
                batch_ids = [row["id"] for row in batch_rows_ids]
                id_placeholders = ",".join("?" for _ in batch_ids)
                update_sql = (
                    f"UPDATE th_translations SET status = ?, "
                    f"last_updated_at = ? WHERE id IN ({id_placeholders})"
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                await cursor.execute(
                    update_sql,
                    [TranslationStatus.TRANSLATING.value, now_iso] + batch_ids,
                )
            id_placeholders_for_select = ",".join("?" for _ in batch_ids)
            find_details_sql = f"""
                SELECT
                    tr.id as translation_id, j.business_id,
                    tr.content_id, tr.context_id,
                    c.value, ctx.value as context
                FROM th_translations tr
                JOIN th_content c ON tr.content_id = c.id
                LEFT JOIN th_contexts ctx ON tr.context_id = ctx.id
                LEFT JOIN th_jobs j ON
                    tr.content_id = j.content_id AND
                    COALESCE(tr.context_id, '') = COALESCE(j.context_id, '')
                WHERE tr.id IN ({id_placeholders_for_select})
                GROUP BY tr.id
            """
            async with self.connection.execute(find_details_sql, batch_ids) as cursor:
                batch_rows_details = await cursor.fetchall()
            batch_items = [
                ContentItem(
                    translation_id=r["translation_id"],
                    business_id=r["business_id"],
                    value=r["value"],
                    context=json.loads(r["context"]) if r["context"] else None,
                    content_id=r["content_id"],
                    context_id=r["context_id"],
                )
                for r in batch_rows_details
            ]
            if not batch_items:
                break
            yield batch_items
            processed_count += len(batch_items)

    async def save_translations(self, results: list[TranslationResult]) -> None:
        if not results:
            return
        params_to_update: list[dict[str, Any]] = [
            {
                "id": res.translation_id,
                "status": res.status.value,
                "translation_content": res.translated_content,
                "engine": res.engine,
                "error": res.error,
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
            }
            for res in results
        ]
        async with self._transaction() as cursor:
            await cursor.executemany(
                """
                UPDATE th_translations SET
                    status = :status,
                    translation_content = :translation_content,
                    engine = :engine,
                    error = :error,
                    last_updated_at = :last_updated_at
                WHERE
                    id = :id AND status = 'TRANSLATING'
                """,
                params_to_update,
            )

    async def get_translation(
        self,
        text_content: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        context_hash = get_context_hash(context)
        sql = """
            SELECT
                tr.id as translation_id,
                tr.translation_content,
                tr.engine,
                tr.error,
                j.business_id
            FROM th_translations tr
            JOIN th_content c ON c.id = tr.content_id
            LEFT JOIN th_contexts ctx ON ctx.id = tr.context_id
            LEFT JOIN th_jobs j ON j.content_id = tr.content_id
                AND COALESCE(j.context_id, '') = COALESCE(tr.context_id, '')
            WHERE
                c.value = ?
                AND tr.lang_code = ?
                AND COALESCE(ctx.context_hash, '__GLOBAL__') = ?
                AND tr.status = ?
            ORDER BY
                j.last_requested_at DESC
            LIMIT 1;
        """
        params = (
            text_content,
            target_lang,
            context_hash,
            TranslationStatus.TRANSLATED.value,
        )
        async with self.connection.execute(sql, params) as cursor:
            row = await cursor.fetchone()
        if row:
            return TranslationResult(
                translation_id=row["translation_id"],
                original_content=text_content,
                translated_content=row["translation_content"],
                target_lang=target_lang,
                status=TranslationStatus.TRANSLATED,
                engine=row["engine"],
                error=row["error"],
                from_cache=True,
                business_id=row["business_id"],
                context_hash=context_hash,
            )
        return None

    async def get_business_id_for_job(
        self, content_id: str, context_id: Optional[str]
    ) -> Optional[str]:
        sql = (
            "SELECT business_id FROM th_jobs "
            "WHERE content_id = ? AND "
            "COALESCE(context_id, '') = COALESCE(?, '') "
            "ORDER BY last_requested_at DESC LIMIT 1"
        )
        async with self.connection.execute(sql, (content_id, context_id)) as cursor:
            row = await cursor.fetchone()
        return cast(Optional[str], row["business_id"] if row else None)

    async def touch_jobs(
        self, business_ids: list[str], cursor: Optional[aiosqlite.Cursor] = None
    ) -> None:
        if not business_ids:
            return

        # 如果提供了游标，则在现有事务中执行
        if cursor is not None:
            placeholders = ",".join("?" for _ in business_ids)
            now_iso = datetime.now(timezone.utc).isoformat()
            sql = (
                f"UPDATE th_jobs SET last_requested_at = ? "
                f"WHERE business_id IN ({placeholders})"
            )
            await cursor.execute(sql, [now_iso] + business_ids)
        else:
            # 否则创建新事务
            async with self._transaction() as tx_cursor:
                placeholders = ",".join("?" for _ in business_ids)
                now_iso = datetime.now(timezone.utc).isoformat()
                sql = (
                    f"UPDATE th_jobs SET last_requested_at = ? "
                    f"WHERE business_id IN ({placeholders})"
                )
                await tx_cursor.execute(sql, [now_iso] + business_ids)

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        if retention_days < 0:
            raise ValueError("retention_days 必须是非负数。")

        async with self._transaction() as cursor:
            cutoff_iso = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).isoformat()
            stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}

            await cursor.execute(
                "SELECT id FROM th_jobs WHERE last_requested_at < ?",
                (cutoff_iso,),
            )
            expired_job_ids = [cast(str, row[0]) for row in await cursor.fetchall()]
            stats["deleted_jobs"] = len(expired_job_ids)
            if not dry_run and expired_job_ids:
                placeholders = ",".join("?" * len(expired_job_ids))
                await cursor.execute(
                    f"DELETE FROM th_jobs WHERE id IN ({placeholders})", expired_job_ids
                )

            await cursor.execute("""
                SELECT c.id FROM th_content c
                WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.content_id = c.id)
                AND NOT EXISTS (
                    SELECT 1 FROM th_translations t
                    WHERE t.content_id = c.id
                )
            """)
            orphan_content_ids = [cast(str, row[0]) for row in await cursor.fetchall()]
            stats["deleted_content"] = len(orphan_content_ids)
            if not dry_run and orphan_content_ids:
                placeholders = ",".join("?" * len(orphan_content_ids))
                await cursor.execute(
                    f"DELETE FROM th_content WHERE id IN ({placeholders})",
                    orphan_content_ids,
                )

            await cursor.execute("""
                SELECT ctx.id FROM th_contexts ctx
                WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.context_id = ctx.id)
                AND NOT EXISTS (
                    SELECT 1 FROM th_translations t
                    WHERE t.context_id = ctx.id
                )
            """)
            orphan_context_ids = [cast(str, row[0]) for row in await cursor.fetchall()]
            stats["deleted_contexts"] = len(orphan_context_ids)
            if not dry_run and orphan_context_ids:
                placeholders = ",".join("?" * len(orphan_context_ids))
                await cursor.execute(
                    f"DELETE FROM th_contexts WHERE id IN ({placeholders})",
                    orphan_context_ids,
                )

            return stats

    async def move_to_dlq(
        self,
        item: ContentItem,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None:
        async with self._transaction() as cursor:
            await cursor.execute(
                "SELECT source_lang_code, lang_code FROM th_translations WHERE id = ?",
                (item.translation_id,),
            )
            translation_row = await cursor.fetchone()
            if not translation_row:
                logger.warning(
                    "尝试移动到 DLQ 的任务已不存在", translation_id=item.translation_id
                )
                return

            context_hash = get_context_hash(item.context)
            params = (
                item.value,
                translation_row["source_lang_code"],
                translation_row["lang_code"],
                context_hash,
                json.dumps(item.context) if item.context else None,
                engine_name,
                engine_version,
                error_message,
            )
            await cursor.execute(
                """
                INSERT INTO th_dead_letter_queue
                (
                    original_content, source_lang_code, target_lang_code, context_hash,
                    context_json, engine_name, engine_version, last_error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
            await cursor.execute(
                "DELETE FROM th_translations WHERE id = ?", (item.translation_id,)
            )
            logger.info("任务已移至死信队列", translation_id=item.translation_id)
