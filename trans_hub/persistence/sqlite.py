# trans_hub/persistence/sqlite.py
"""提供了基于 aiosqlite 的持久化实现。"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import aiosqlite
import structlog

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.persistence.utils import generate_uuid
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class SQLitePersistenceHandler(PersistenceHandler):
    """`PersistenceHandler` 协议的 SQLite 实现。"""

    SUPPORTS_NOTIFICATIONS = False

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        logger.info("SQLite 持久层已配置", db_path=self.db_path)

    async def connect(self) -> None:
        """建立与 SQLite 数据库的连接。"""
        try:
            is_memory_db = self.db_path == ":memory:"
            self._conn = await aiosqlite.connect(self.db_path, isolation_level=None)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA foreign_keys = ON")
            if not is_memory_db:
                await self._conn.execute("PRAGMA journal_mode=WAL")
                logger.info("SQLite WAL 模式已启用。")
            logger.info("SQLite 数据库连接已建立", db_path=self.db_path)
        except aiosqlite.Error as e:
            logger.error("连接 SQLite 数据库失败", exc_info=True)
            raise DatabaseError(f"数据库连接失败: {e}") from e

    async def close(self) -> None:
        """关闭 SQLite 数据库连接。"""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("SQLite 数据库连接已关闭", db_path=self.db_path)

    @property
    def connection(self) -> aiosqlite.Connection:
        if not self._conn:
            raise DatabaseError("数据库未连接或已关闭。请先调用 connect()。")
        return self._conn

    @asynccontextmanager
    async def _transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """提供一个手动的、原子的数据库事务上下文。"""
        transaction_started = False
        try:
            try:
                await self.connection.execute("BEGIN")
                transaction_started = True
            except aiosqlite.OperationalError as e:
                if "cannot start a transaction within a transaction" in str(e):
                    transaction_started = False
                else:
                    raise
            yield self.connection
            if transaction_started:
                await self.connection.commit()
        except Exception:
            logger.error("SQLite 事务执行失败，正在回滚", exc_info=True)
            if self._conn and transaction_started:
                await self.connection.rollback()
            raise

    async def reset_stale_tasks(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._transaction() as tx:
            cursor = await tx.execute(
                """
                UPDATE th_translations
                SET status = ?, error = NULL, last_updated_at = ?
                WHERE status = ?
                """,
                (
                    TranslationStatus.PENDING.value,
                    now_iso,
                    TranslationStatus.TRANSLATING.value,
                ),
            )
            if cursor.rowcount > 0:
                logger.warning("系统自愈：重置了遗留的翻译任务", count=cursor.rowcount)
            await cursor.close()

    def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: int | None = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        async def _internal_generator() -> AsyncGenerator[list[ContentItem], None]:
            processed_count = 0
            while limit is None or processed_count < limit:
                current_batch_size = min(
                    batch_size,
                    (limit - processed_count) if limit is not None else batch_size,
                )
                if current_batch_size <= 0:
                    break

                batch_items: list[ContentItem] = []
                async with self._transaction() as tx:
                    status_placeholders = ",".join("?" for _ in statuses)
                    find_details_sql = f"""
                        SELECT
                            t.id as translation_id,
                            c.business_id,
                            t.content_id,
                            t.context_id,
                            t.source_lang,
                            c.source_payload_json,
                            ctx.context_payload_json
                        FROM th_translations t
                        JOIN th_content c ON t.content_id = c.id
                        LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
                        WHERE t.lang_code = ? AND t.status IN ({status_placeholders})
                        ORDER BY t.context_id, t.last_updated_at ASC
                        LIMIT ?
                    """
                    params = (
                        [lang_code] + [s.value for s in statuses] + [current_batch_size]
                    )
                    cursor = await tx.execute(find_details_sql, params)
                    rows = await cursor.fetchall()
                    await cursor.close()

                    if not rows:
                        break

                    batch_ids = [row["translation_id"] for row in rows]
                    id_placeholders = ",".join("?" for _ in batch_ids)
                    now_iso = datetime.now(timezone.utc).isoformat()

                    await tx.execute(
                        f"UPDATE th_translations SET status = ?, last_updated_at = ? "
                        f"WHERE id IN ({id_placeholders})",
                        [TranslationStatus.TRANSLATING.value, now_iso] + batch_ids,
                    )

                    batch_items = [
                        ContentItem(
                            translation_id=r["translation_id"],
                            business_id=r["business_id"],
                            content_id=r["content_id"],
                            context_id=r["context_id"],
                            source_payload=json.loads(r["source_payload_json"]),
                            context=(
                                json.loads(r["context_payload_json"])
                                if r["context_payload_json"]
                                else None
                            ),
                            source_lang=r["source_lang"],
                        )
                        for r in rows
                    ]

                if not batch_items:
                    break
                yield batch_items
                processed_count += len(batch_items)

        return _internal_generator()

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> tuple[str, str | None]:
        async with self._transaction() as tx:
            cursor = await tx.execute(
                "SELECT id FROM th_content WHERE business_id = ?", (business_id,)
            )
            content_row = await cursor.fetchone()
            await cursor.close()
            now_iso = datetime.now(timezone.utc).isoformat()
            if content_row:
                content_id = cast(str, content_row["id"])
                await tx.execute(
                    "UPDATE th_content SET source_payload_json = ?, updated_at = ? WHERE id = ?",
                    (
                        json.dumps(source_payload, ensure_ascii=False),
                        now_iso,
                        content_id,
                    ),
                )
            else:
                content_id = generate_uuid()
                await tx.execute(
                    "INSERT INTO th_content (id, business_id, source_payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        content_id,
                        business_id,
                        json.dumps(source_payload, ensure_ascii=False),
                        now_iso,
                        now_iso,
                    ),
                )
            context_id: str | None = None
            if context:
                context_hash = get_context_hash(context)
                cursor = await tx.execute(
                    "SELECT id FROM th_contexts WHERE context_hash = ?", (context_hash,)
                )
                context_row = await cursor.fetchone()
                await cursor.close()
                if context_row:
                    context_id = cast(str, context_row["id"])
                else:
                    context_id = generate_uuid()
                    await tx.execute(
                        "INSERT INTO th_contexts (id, context_hash, context_payload_json, created_at) VALUES (?, ?, ?, ?)",
                        (
                            context_id,
                            context_hash,
                            json.dumps(context, ensure_ascii=False),
                            now_iso,
                        ),
                    )
            cursor = await tx.execute(
                "SELECT id FROM th_jobs WHERE content_id = ?", (content_id,)
            )
            job_row = await cursor.fetchone()
            await cursor.close()
            if job_row:
                await tx.execute(
                    "UPDATE th_jobs SET last_requested_at = ? WHERE id = ?",
                    (now_iso, job_row["id"]),
                )
            else:
                await tx.execute(
                    "INSERT INTO th_jobs (id, content_id, last_requested_at) VALUES (?, ?, ?)",
                    (generate_uuid(), content_id, now_iso),
                )
        return content_id, context_id

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: str | None,
        target_langs: list[str],
        source_lang: str | None,
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._transaction() as tx:
            if force_retranslate and target_langs:
                placeholders = ",".join("?" for _ in target_langs)
                update_params: list[Any] = [
                    TranslationStatus.PENDING.value,
                    now_iso,
                    engine_version,
                    source_lang,
                    content_id,
                ]
                context_clause = (
                    "context_id = ?" if context_id else "context_id IS NULL"
                )
                if context_id:
                    update_params.append(context_id)
                update_params.extend(target_langs)
                sql = f"""
                    UPDATE th_translations
                    SET status = ?, last_updated_at = ?, engine_version = ?, source_lang = ?,
                        translation_payload_json = NULL, error = NULL
                    WHERE content_id = ? AND {context_clause} AND lang_code IN ({placeholders})
                """
                await tx.execute(sql, tuple(update_params))

            insert_sql = """
                INSERT OR IGNORE INTO th_translations
                (id, content_id, context_id, lang_code, source_lang, engine_version, created_at, last_updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """
            params = [
                (
                    generate_uuid(),
                    content_id,
                    context_id,
                    lang,
                    source_lang,
                    engine_version,
                    now_iso,
                    now_iso,
                )
                for lang in target_langs
            ]
            if params:
                await tx.executemany(insert_sql, params)

    async def save_translation_results(self, results: list[TranslationResult]) -> None:
        if not results:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        params = [
            {
                "id": res.translation_id,
                "status": res.status.value,
                "payload": json.dumps(res.translated_payload, ensure_ascii=False)
                if res.translated_payload
                else None,
                "engine": res.engine,
                "error": res.error,
                "now": now_iso,
            }
            for res in results
        ]
        async with self._transaction() as tx:
            await tx.executemany(
                """
                UPDATE th_translations
                SET status = :status, translation_payload_json = :payload, engine = :engine,
                    error = :error, last_updated_at = :now
                WHERE id = :id AND status = 'TRANSLATING'
                """,
                params,
            )

    async def find_translation(
        self, business_id: str, target_lang: str, context: dict[str, Any] | None = None
    ) -> TranslationResult | None:
        context_hash = get_context_hash(context)
        sql = """
            SELECT t.id as translation_id, c.source_payload_json, t.translation_payload_json,
                   t.status, t.engine, t.error
            FROM th_translations t
            JOIN th_content c ON t.content_id = c.id
            LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
            WHERE c.business_id = ? AND t.lang_code = ? AND COALESCE(ctx.context_hash, '__GLOBAL__') = ?
        """
        cursor = await self.connection.execute(
            sql, (business_id, target_lang, context_hash)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if not row:
            return None
        return TranslationResult(
            translation_id=row["translation_id"],
            business_id=business_id,
            original_payload=json.loads(row["source_payload_json"]),
            translated_payload=json.loads(row["translation_payload_json"])
            if row["translation_payload_json"]
            else None,
            target_lang=target_lang,
            status=TranslationStatus(row["status"]),
            engine=row["engine"],
            from_cache=True,
            error=row["error"],
            context_hash=context_hash,
        )

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False, _now: datetime | None = None
    ) -> dict[str, int]:
        now = _now if _now is not None else datetime.now(timezone.utc)
        cutoff_date = (now.date() - timedelta(days=retention_days)).isoformat()
        stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}

        async with self._transaction() as tx:
            if dry_run:
                cursor = await tx.execute(
                    "SELECT COUNT(*) FROM th_jobs WHERE DATE(last_requested_at) < ?",
                    (cutoff_date,),
                )
                res = await cursor.fetchone()
                stats["deleted_jobs"] = res[0] if res else 0
            else:
                cursor = await tx.execute(
                    "DELETE FROM th_jobs WHERE DATE(last_requested_at) < ?",
                    (cutoff_date,),
                )
                stats["deleted_jobs"] = cursor.rowcount
            await cursor.close()

            orphan_content_sql = """
                FROM th_content
                WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.content_id = th_content.id)
                  AND NOT EXISTS (SELECT 1 FROM th_translations t WHERE t.content_id = th_content.id)
            """
            if dry_run:
                cursor = await tx.execute(f"SELECT COUNT(*) {orphan_content_sql}")
                res = await cursor.fetchone()
                stats["deleted_content"] = res[0] if res else 0
            else:
                cursor = await tx.execute(
                    f"DELETE FROM th_content WHERE id IN (SELECT id {orphan_content_sql})"
                )
                stats["deleted_content"] = cursor.rowcount
            await cursor.close()

            orphan_context_sql = """
                FROM th_contexts
                WHERE NOT EXISTS (SELECT 1 FROM th_translations t WHERE t.context_id = th_contexts.id)
            """
            if dry_run:
                cursor = await tx.execute(f"SELECT COUNT(*) {orphan_context_sql}")
                res = await cursor.fetchone()
                stats["deleted_contexts"] = res[0] if res else 0
            else:
                cursor = await tx.execute(
                    f"DELETE FROM th_contexts WHERE id IN (SELECT id {orphan_context_sql})"
                )
                stats["deleted_contexts"] = cursor.rowcount
            await cursor.close()
        return stats

    async def move_to_dlq(
        self,
        item: ContentItem,
        target_lang: str,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None:
        async with self._transaction() as tx:
            await tx.execute(
                """
                INSERT INTO th_dead_letter_queue (translation_id, original_payload_json, context_payload_json,
                     target_lang_code, last_error_message, failed_at, engine_name, engine_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.translation_id,
                    json.dumps(item.source_payload, ensure_ascii=False),
                    json.dumps(item.context, ensure_ascii=False)
                    if item.context
                    else None,
                    target_lang,
                    error_message,
                    datetime.now(timezone.utc).isoformat(),
                    engine_name,
                    engine_version,
                ),
            )
            await tx.execute(
                "DELETE FROM th_translations WHERE id = ?", (item.translation_id,)
            )
        logger.info("任务已成功移至死信队列", translation_id=item.translation_id)

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        """[实现] SQLite 不支持 LISTEN/NOTIFY，因此返回一个无操作的异步生成器。"""

        # [核心修复] 使用 `if False: yield ""` 模式创建一个正确的、
        # 类型为 AsyncGenerator[str, None] 的无操作异步生成器。
        # 之前的 `yield` (无值) 会被 mypy 推断为 AsyncGenerator[None, None]，
        # 导致与接口协议的类型不匹配。
        async def _empty_generator() -> AsyncGenerator[str, None]:
            if False:
                yield ""  # 提供一个假的 str 值以满足类型检查器

        return _empty_generator()
