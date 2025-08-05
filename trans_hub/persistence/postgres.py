# trans_hub/persistence/postgres.py
"""
提供了基于 asyncpg 的 PostgreSQL 持久化实现。

本模块是 `PersistenceHandler` 协议的 PostgreSQL 具体实现，
为 Trans-Hub 提供了高性能、高并发的生产级数据后端。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg
import structlog
from asyncpg.exceptions import UniqueViolationError

from trans_hub.core.exceptions import DatabaseError
from trans_hub.core.interfaces import PersistenceHandler
from trans_hub.core.types import (
    ContentItem,
    TranslationResult,
    TranslationStatus,
)
from trans_hub.utils import get_context_hash

logger = structlog.get_logger(__name__)


class PostgresPersistenceHandler(PersistenceHandler):
    """`PersistenceHandler` 协议的 PostgreSQL 实现。"""

    SUPPORTS_NOTIFICATIONS = True
    NOTIFICATION_CHANNEL = "new_translation_task"

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        logger.info("PostgreSQL 持久层已配置")

    async def connect(self) -> None:
        """建立与 PostgreSQL 数据库的连接池。"""
        if self._pool:
            return
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self.dsn, min_size=2, max_size=10
            )
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            logger.info("PostgreSQL 数据库连接池已建立并验证成功")
        except (asyncpg.PostgresError, OSError) as e:
            logger.error("连接 PostgreSQL 数据库失败", exc_info=True)
            raise DatabaseError(f"数据库连接失败: {e}") from e

    def listen_for_notifications(self) -> AsyncGenerator[str, None]:
        async def _internal_generator() -> AsyncGenerator[str, None]:
            if not self.SUPPORTS_NOTIFICATIONS:
                if False:
                    yield
                return

            conn: Optional[asyncpg.Connection] = None
            q: asyncio.Queue[str] = asyncio.Queue()

            class CallbackHandler:
                def __init__(self, queue: asyncio.Queue[str]):
                    self.queue = queue

                async def __call__(
                    self,
                    connection: asyncpg.Connection,
                    pid: int,
                    channel: str,
                    payload: str,
                ) -> None:
                    await self.queue.put(payload)

            callback_handler = CallbackHandler(q)

            while True:
                try:
                    conn = await self.pool.acquire()
                    await conn.add_listener(self.NOTIFICATION_CHANNEL, callback_handler)
                    logger.info(
                        "数据库通知监听器已启动", channel=self.NOTIFICATION_CHANNEL
                    )

                    while True:
                        payload = await q.get()
                        yield payload
                except (asyncpg.PostgresError, OSError) as e:
                    logger.error("通知监听器连接丢失，将在5秒后重试...", error=e)
                    await asyncio.sleep(5)
                finally:
                    if conn:
                        try:
                            await conn.remove_listener(
                                self.NOTIFICATION_CHANNEL, callback_handler
                            )
                        except asyncpg.InterfaceError:
                            pass
                        await self.pool.release(conn)
                        conn = None

        return _internal_generator()

    async def close(self) -> None:
        """关闭 PostgreSQL 数据库连接池。"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL 数据库连接池已关闭")

    @property
    def pool(self) -> asyncpg.Pool:
        """获取活动的连接池实例。"""
        if not self._pool:
            raise DatabaseError("数据库未连接或已关闭。请先调用 connect()。")
        return self._pool

    @asynccontextmanager
    async def _transaction(
        self,
    ) -> AsyncGenerator[asyncpg.Connection, None]:
        """提供一个原子的数据库事务上下文。"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def reset_stale_tasks(self) -> None:
        """[实现] 在启动时重置所有处于“TRANSLATING”状态的旧任务为“PENDING”。"""
        sql = """
            UPDATE th_translations
            SET status = $1, error = NULL, last_updated_at = now()
            WHERE status = $2;
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                sql,
                TranslationStatus.PENDING.value,
                TranslationStatus.TRANSLATING.value,
            )
            updated_count = int(result.split(" ")[1]) if result else 0
            if updated_count > 0:
                logger.warning("系统自愈：重置了遗留的翻译任务", count=updated_count)

    async def stream_translatable_items(
        self,
        lang_code: str,
        statuses: list[TranslationStatus],
        batch_size: int,
        limit: Optional[int] = None,
    ) -> AsyncGenerator[list[ContentItem], None]:
        """[实现] 以流式方式获取待处理的翻译任务批次。"""
        processed_count = 0
        while limit is None or processed_count < limit:
            current_batch_size = min(
                batch_size,
                (limit - processed_count) if limit is not None else batch_size,
            )
            if current_batch_size <= 0:
                break

            batch_items: list[ContentItem] = []
            try:
                async with self._transaction() as conn:
                    find_ids_sql = """
                        SELECT id FROM th_translations
                        WHERE lang_code = $1 AND status = ANY($2::text[])
                        ORDER BY last_updated_at ASC
                        LIMIT $3
                        FOR UPDATE SKIP LOCKED;
                    """
                    status_values = [s.value for s in statuses]
                    locked_rows = await conn.fetch(
                        find_ids_sql, lang_code, status_values, current_batch_size
                    )
                    if not locked_rows:
                        break

                    batch_ids = [row["id"] for row in locked_rows]

                    await conn.execute(
                        """
                        UPDATE th_translations
                        SET status = $1, last_updated_at = now()
                        WHERE id = ANY($2::uuid[]);
                        """,
                        TranslationStatus.TRANSLATING.value,
                        batch_ids,
                    )

                    find_details_sql = """
                        SELECT
                            t.id as translation_id,
                            c.business_id,
                            t.content_id,
                            t.context_id,
                            c.source_payload_json,
                            ctx.context_payload_json
                        FROM th_translations t
                        JOIN th_content c ON t.content_id = c.id
                        LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
                        WHERE t.id = ANY($1::uuid[]);
                    """
                    detail_rows = await conn.fetch(find_details_sql, batch_ids)

                    batch_items = [
                        ContentItem(
                            translation_id=str(r["translation_id"]),
                            business_id=r["business_id"],
                            content_id=str(r["content_id"]),
                            context_id=str(r["context_id"])
                            if r["context_id"]
                            else None,
                            source_payload=json.loads(r["source_payload_json"]),
                            context=(
                                json.loads(r["context_payload_json"])
                                if r["context_payload_json"]
                                else None
                            ),
                        )
                        for r in detail_rows
                    ]
            except asyncpg.PostgresError as e:
                raise DatabaseError(f"流式获取任务失败: {e}") from e

            if not batch_items:
                break

            yield batch_items
            processed_count += len(batch_items)

    async def save_translation_results(
        self,
        results: list[TranslationResult],
    ) -> None:
        """[实现] 将一批已完成的翻译结果保存到数据库。"""
        if not results:
            return

        params = [
            (
                res.status.value,
                json.dumps(res.translated_payload) if res.translated_payload else None,
                res.engine,
                res.error,
                res.translation_id,
            )
            for res in results
        ]

        sql = """
            UPDATE th_translations
            SET
                status = $1,
                translation_payload_json = $2::jsonb,
                engine = $3,
                error = $4,
                last_updated_at = now()
            WHERE id = $5::uuid AND status = 'TRANSLATING';
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(sql, params)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"保存翻译结果失败: {e}") from e

    async def ensure_content_and_context(
        self,
        business_id: str,
        source_payload: dict[str, Any],
        context: Optional[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        try:
            async with self._transaction() as conn:
                content_sql = """
                    INSERT INTO th_content (business_id, source_payload_json)
                    VALUES ($1, $2)
                    ON CONFLICT (business_id) DO UPDATE
                    SET source_payload_json = EXCLUDED.source_payload_json,
                        updated_at = now()
                    RETURNING id;
                """
                content_id_rec = await conn.fetchrow(
                    content_sql, business_id, json.dumps(source_payload)
                )
                content_id = str(content_id_rec["id"])

                context_id: Optional[str] = None
                if context:
                    context_hash = get_context_hash(context)
                    context_sql = """
                        INSERT INTO th_contexts (context_hash, context_payload_json)
                        VALUES ($1, $2)
                        ON CONFLICT (context_hash) DO UPDATE
                        SET context_payload_json = EXCLUDED.context_payload_json
                        RETURNING id;
                    """
                    context_id_rec = await conn.fetchrow(
                        context_sql, context_hash, json.dumps(context)
                    )
                    context_id = str(context_id_rec["id"])

                job_sql = """
                    INSERT INTO th_jobs (content_id, last_requested_at)
                    VALUES ($1, now())
                    ON CONFLICT (content_id) DO UPDATE
                    SET last_requested_at = now();
                """
                await conn.execute(job_sql, content_id)

                return content_id, context_id
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"确保内容和上下文失败: {e}") from e

    async def create_pending_translations(
        self,
        content_id: str,
        context_id: Optional[str],
        target_langs: list[str],
        source_lang: Optional[str],
        engine_version: str,
        force_retranslate: bool = False,
    ) -> None:
        try:
            async with self._transaction() as conn:
                if force_retranslate:
                    update_clause = """
                        UPDATE SET status = 'PENDING',
                                   engine_version = EXCLUDED.engine_version,
                                   translation_payload_json = NULL,
                                   error = NULL,
                                   last_updated_at = now()
                    """
                else:
                    update_clause = "NOTHING"

                sql = f"""
                    INSERT INTO th_translations (
                        content_id, context_id, lang_code, engine_version
                    )
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (content_id, context_id, lang_code)
                    DO {update_clause};
                """
                params = [
                    (content_id, context_id, lang, engine_version)
                    for lang in target_langs
                ]
                await conn.executemany(sql, params)
        except (UniqueViolationError, asyncpg.PostgresError) as e:
            raise DatabaseError(f"创建待处理翻译失败: {e}") from e

    async def find_translation(
        self,
        business_id: str,
        target_lang: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[TranslationResult]:
        context_hash = get_context_hash(context)
        sql = """
            SELECT
                t.id AS translation_id,
                c.source_payload_json,
                t.translation_payload_json,
                t.status,
                t.engine,
                t.error
            FROM th_translations t
            JOIN th_content c ON t.content_id = c.id
            LEFT JOIN th_contexts ctx ON t.context_id = ctx.id
            WHERE c.business_id = $1
              AND t.lang_code = $2
              AND COALESCE(ctx.context_hash, '__GLOBAL__') = $3;
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(sql, business_id, target_lang, context_hash)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"查找翻译失败: {e}") from e

        if not row:
            return None

        original_payload = json.loads(row["source_payload_json"])
        translated_payload = (
            json.loads(row["translation_payload_json"])
            if row["translation_payload_json"]
            else None
        )

        return TranslationResult(
            translation_id=str(row["translation_id"]),
            business_id=business_id,
            original_payload=original_payload,
            translated_payload=translated_payload,
            target_lang=target_lang,
            status=TranslationStatus(row["status"]),
            engine=row["engine"],
            from_cache=True,
            error=row["error"],
            context_hash=context_hash,
        )

    async def garbage_collect(
        self, retention_days: int, dry_run: bool = False
    ) -> dict[str, int]:
        """[实现] 执行垃圾回收。"""
        stats = {"deleted_jobs": 0, "deleted_content": 0, "deleted_contexts": 0}
        cutoff_date_sql = "now() - interval '%s days'" % retention_days

        try:
            async with self._transaction() as conn:
                del_jobs_sql = (
                    f"DELETE FROM th_jobs WHERE last_requested_at < {cutoff_date_sql} "
                    "RETURNING id;"
                )
                if dry_run:
                    del_jobs_sql = (
                        f"SELECT id FROM th_jobs WHERE last_requested_at "
                        f"< {cutoff_date_sql};"
                    )

                deleted_jobs = await conn.fetch(del_jobs_sql)
                stats["deleted_jobs"] = len(deleted_jobs)

                del_content_sql = """
                    DELETE FROM th_content c
                    WHERE NOT EXISTS (SELECT 1 FROM th_jobs j WHERE j.content_id = c.id)
                    RETURNING id;
                """
                if dry_run:
                    del_content_sql = """
                        SELECT id FROM th_content c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_jobs j WHERE j.content_id = c.id
                        );
                    """

                deleted_content = await conn.fetch(del_content_sql)
                stats["deleted_content"] = len(deleted_content)

                del_contexts_sql = """
                    DELETE FROM th_contexts ctx
                    WHERE NOT EXISTS (
                        SELECT 1 FROM th_translations t WHERE t.context_id = ctx.id
                    ) RETURNING id;
                """
                if dry_run:
                    del_contexts_sql = """
                        SELECT id FROM th_contexts ctx
                        WHERE NOT EXISTS (
                            SELECT 1 FROM th_translations t
                            WHERE t.context_id = ctx.id
                        );
                    """

                deleted_contexts = await conn.fetch(del_contexts_sql)
                stats["deleted_contexts"] = len(deleted_contexts)

                if dry_run:
                    raise asyncpg.exceptions.RollbackTransactionError("Dry run")
            return stats
        except asyncpg.exceptions.RollbackTransactionError:
            logger.info("垃圾回收 (dry run) 完成，事务已回滚。")
            return stats
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"垃圾回收失败: {e}") from e

    async def move_to_dlq(
        self,
        item: ContentItem,
        target_lang: str,
        error_message: str,
        engine_name: str,
        engine_version: str,
    ) -> None:
        """[实现] 将任务移至死信队列。"""
        try:
            async with self._transaction() as conn:
                await conn.execute(
                    """
                    INSERT INTO th_dead_letter_queue (
                        translation_id, original_payload_json, context_payload_json,
                        target_lang_code, last_error_message,
                        engine_name, engine_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    item.translation_id,
                    json.dumps(item.source_payload),
                    json.dumps(item.context) if item.context else None,
                    target_lang,
                    error_message,
                    engine_name,
                    engine_version,
                )
                await conn.execute(
                    "DELETE FROM th_translations WHERE id = $1", item.translation_id
                )
            logger.info("任务已成功移至死信队列", translation_id=item.translation_id)
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"移动到死信队列失败: {e}") from e
